# Payments: live Paystack when PAYSTACK_SECRET_KEY is set, built-in mock otherwise.
# Both flows: initialize -> hosted checkout (Paystack page or in-app mock) -> confirm/callback.
import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

import config
import schemas
import services.paystack as paystack
from database import get_db
from deps import current_user, make_reference
from services.notify import send_notification

router = APIRouter(tags=["payments"])

METHOD_LABELS = {"card": "Card", "bank_transfer": "Bank Transfer", "ussd": "USSD", "qr": "QR / Bank app"}


def _contact(row: sqlite3.Row):
    try:
        return (json.loads(row["details"]).get("contact") or {})
    except Exception:
        return {}


def _settle(db: sqlite3.Connection, booking_id: int, method: str) -> dict:
    row = db.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
    db.execute("UPDATE bookings SET status='confirmed', updated_at=datetime('now') WHERE id=? AND status!='confirmed'",
               (booking_id,))
    db.execute("UPDATE payments SET status='paid', method=?, paid_at=datetime('now') WHERE booking_id=? AND status='pending'",
               (method, booking_id))
    c = _contact(row)
    send_notification(db, row["user_id"], "Payment successful",
                      f"Reference {row['reference']} is confirmed. Safe travels!",
                      email=c.get("email", ""), phone=c.get("phone", ""))
    return {"ok": True, "booking_status": "confirmed", "reference": row["reference"]}


@router.post("/payments/initialize")
def initialize(body: schemas.PaymentInitIn, db: sqlite3.Connection = Depends(get_db),
               user=Depends(current_user)):
    row = db.execute("SELECT * FROM bookings WHERE reference=? AND user_id=?",
                     (body.reference, user["id"])).fetchone()
    if row is None:
        raise HTTPException(404, "Booking not found")
    if row["status"] == "cancelled":
        raise HTTPException(400, "This booking was cancelled")
    if row["status"] == "confirmed":
        return {"already_paid": True, "authorization_url": f"/#/booking/{row['reference']}"}
    existing = db.execute(
        "SELECT reference FROM payments WHERE booking_id=? AND status='pending' ORDER BY id DESC LIMIT 1",
        (row["id"],)).fetchone()
    gateway_ref = existing["reference"] if existing else "pay-" + make_reference("")[3:]
    if not existing:
        db.execute("INSERT INTO payments (reference, booking_id, amount) VALUES (?,?,?)",
                   (gateway_ref, row["id"], row["amount"]))
    # --- live mode ---
    if paystack.configured():
        try:
            url = paystack.initialize(user["email"], row["amount"], gateway_ref,
                                      f"{config.BASE_URL}/api/payments/callback", row["reference"])
            return {"authorization_url": url, "gateway_reference": gateway_ref,
                    "amount": row["amount"], "currency": row["currency"], "live": True}
        except Exception as exc:
            raise HTTPException(502, f"Payment gateway error: {exc}")
    # --- mock mode (dev/demo) ---
    return {"authorization_url": f"/#/pay/{row['reference']}?gateway={gateway_ref}",
            "gateway_reference": gateway_ref, "amount": row["amount"],
            "currency": row["currency"], "live": False}


@router.post("/payments/confirm")
def confirm(body: schemas.PaymentConfirmIn, db: sqlite3.Connection = Depends(get_db),
            user=Depends(current_user)):
    """Mock-mode settlement. In live mode the user pays on Paystack's page instead."""
    row = db.execute("SELECT * FROM bookings WHERE reference=? AND user_id=?",
                     (body.reference, user["id"])).fetchone()
    if row is None:
        raise HTTPException(404, "Booking not found")
    if row["status"] == "confirmed":
        return {"ok": True, "booking_status": "confirmed", "reference": row["reference"]}
    if row["status"] == "cancelled":
        raise HTTPException(400, "This booking was cancelled")
    if paystack.configured():
        raise HTTPException(400, "Live mode: complete payment on the Paystack checkout page")
    return _settle(db, row["id"], METHOD_LABELS.get(body.method, body.method))


@router.get("/payments/callback")
def callback(request: Request, reference: str = "", trxref: str = "",
             db: sqlite3.Connection = Depends(get_db)):
    """Browser return URL. Live mode verifies with Paystack; mock mode settles directly."""
    gateway_ref = trxref or reference
    pay = db.execute("SELECT * FROM payments WHERE reference=?", (gateway_ref,)).fetchone()
    if pay is None:
        return RedirectResponse(f"/#/booking/{reference}?paid=0")
    booking = db.execute("SELECT reference FROM bookings WHERE id=?", (pay["booking_id"],)).fetchone()
    ok = False
    if paystack.configured():
        try:
            ok, data = paystack.verify(gateway_ref)
            expected = int(round(pay["amount"] * 100))
            ok = ok and data.get("amount") == expected
        except Exception:
            ok = False
    else:
        ok = True
    if ok and booking:
        _settle(db, pay["booking_id"], "Card")
    return RedirectResponse(f"/#/booking/{booking['reference'] if booking else reference}?paid={1 if ok else 0}")


@router.post("/payments/webhook")
async def webhook(request: Request, db: sqlite3.Connection = Depends(get_db)):
    """Server-to-server confirmation. Live mode requires a valid Paystack signature."""
    raw = await request.body()
    payload = json.loads(raw or b"{}")
    if paystack.configured():
        sig = request.headers.get("x-paystack-signature", "")
        if not paystack.valid_signature(raw, sig):
            raise HTTPException(401, "Invalid webhook signature")
    if payload.get("event") in ("charge.success", "charge.success.replay"):
        gateway_ref = (payload.get("data") or {}).get("reference", "")
        row = db.execute(
            """SELECT b.id FROM payments p JOIN bookings b ON b.id=p.booking_id
               WHERE p.reference=? AND p.status='pending'""", (gateway_ref,)).fetchone()
        if row:
            _settle(db, row["id"], "Card")
    return {"ok": True}
