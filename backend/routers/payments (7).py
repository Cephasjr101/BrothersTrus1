# Payments: LIVE Paystack only - there is no demo/mock mode.
# Primary: API checkout (requires PAYSTACK_SECRET_KEY) -> automatic confirmation.
# Fallback: hosted Payment Page (PAYSTACK_PAYMENT_PAGE_URL) when the API key is
#   not configured. Page payments use Paystack-generated references, so they
#   CANNOT be auto-matched by the webhook - confirm them manually in the admin
#   dashboard against the Paystack dashboard payouts.
import json
import os
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

import config
import schemas
import services.airlines as air
import services.paystack as paystack
from database import get_db
from deps import current_user, make_reference, notify
from services.notify import send_notification

router = APIRouter(tags=["payments"])

METHOD_LABELS = {"card": "Card", "bank_transfer": "Bank Transfer", "ussd": "USSD", "qr": "QR / Bank app",
                   "momo": "MoMo", "office": "Pay at Office"}

# Hosted Paystack Payment Page (https://paystack.shop/pay/...) - fallback only,
# active when the API secret key is absent. Manual reconciliation required.
PAYMENT_PAGE_URL = os.getenv("PAYSTACK_PAYMENT_PAGE_URL", "").strip()


def _via_payment_page() -> str:
    """Return the Payment Page URL when API checkout is unavailable."""
    if PAYMENT_PAGE_URL and not paystack.configured():
        return PAYMENT_PAGE_URL
    return ""


def _require_gateway():
    """Fail closed: every charging endpoint 503s unless Paystack is configured."""
    if not paystack.configured():
        raise HTTPException(503, "Payment gateway not configured. Set PAYSTACK_SECRET_KEY.")


def _contact(row: sqlite3.Row):
    try:
        return (json.loads(row["details"]).get("contact") or {})
    except Exception:
        return {}


def _working_deadline(days: int = 4) -> str:
    """N working days from today (skips weekends) — ISO date."""
    from datetime import date, timedelta
    d = date.today()
    added = 0
    while added < days:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d.isoformat()


def _settle(db: sqlite3.Connection, booking_id: int, method: str) -> dict:
    """Mark pending payments paid, then confirm the booking ONLY when the
    cumulative paid amount covers the full total (supports installments)."""
    row = db.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
    db.execute("UPDATE payments SET status='paid', method=?, paid_at=datetime('now') WHERE booking_id=? AND status='pending'",
               (method, booking_id))
    total = round(sum(a for (a,) in db.execute(
        "SELECT amount FROM payments WHERE booking_id=? AND status='paid'", (booking_id,))))
    c = _contact(row)
    if total >= row["amount"] - 0.01:
        db.execute("UPDATE bookings SET status='confirmed', updated_at=datetime('now') WHERE id=? AND status!='confirmed'",
                   (booking_id,))
        _maybe_ticket_flight(db, row)
        send_notification(db, row["user_id"], "Payment successful",
                          f"Reference {row['reference']} is confirmed. Safe travels!",
                          email=c.get("email", ""), phone=c.get("phone", ""))
        return {"ok": True, "booking_status": "confirmed", "reference": row["reference"]}
    # partial payment: record progress, keep booking pending
    details = json.loads(row["details"])
    inst = details.get("installments") or {}
    inst["paid_so_far"] = total
    inst["remaining"] = round(row["amount"] - total)
    db.execute("UPDATE bookings SET details=? WHERE id=?", (json.dumps(details), booking_id))
    send_notification(db, row["user_id"], "Part payment received",
                      f"Reference {row['reference']}: GH\u00a2{total:,} received. "
                      f"Balance of GH\u00a2{inst['remaining']:,} is due by the agreed date.",
                      email=c.get("email", ""), phone=c.get("phone", ""))
    return {"ok": True, "booking_status": "pending", "paid_so_far": total,
            "remaining": inst["remaining"], "reference": row["reference"]}


def _maybe_ticket_flight(db, booking_row) -> None:
    """Live fulfilment after payment: Duffel airline orders and LiteAPI hotel
    reservations. Failures never block the booking — they're recorded in the
    booking details for staff follow-up."""
    details = {}
    try:
        details = json.loads(booking_row["details"])
        if booking_row["type"] == "flight" and air.duffel_configured() and "legs" in details:
            inst = details.get("instant_order") or {}
            hold_id = (details.get("hold_order") or {}).get("order_id")
            if inst.get("order_id"):
                # instant order (deferred payment) - already ticketed at booking time
                details["tickets"] = [{"leg": "instant order (deferred payment)", **inst}]
            elif hold_id:
                # seat was locked at booking time - just capture it now
                details["tickets"] = [{"leg": "held order (captured after payment)",
                                       **air.confirm_held_order(hold_id)}]
            else:
                tickets = []
                for leg in details["legs"]:
                    if leg.get("provider") != "duffel":
                        continue
                    tickets.append({"leg": f"{leg.get('origin')}\u2192{leg.get('dest')}",
                                    **air.ticket_order(leg["flight_key"],
                                                       details.get("passengers") or [],
                                                       details.get("contact") or {})})
                if tickets:
                    details["tickets"] = tickets
        elif booking_row["type"] == "hotel" and details.get("provider") == "liteapi":
            import services.hotelsapi as hb
            travelers = json.loads(booking_row["travelers"])
            details["hotel_confirmation"] = hb.book(
                details["hotel_id"], details["room_key"], details["checkin"],
                details["checkout"], details["rooms"], details["guests"],
                travelers[0] if travelers else "Guest",
                details.get("contact") or {}, travelers)
        else:
            return
        db.execute("UPDATE bookings SET details=? WHERE id=?",
                   (json.dumps(details), booking_row["id"]))
    except Exception as exc:   # never break payment confirmation over fulfilment
        try:
            details["ticketing_error"] = str(exc)[:300]
            db.execute("UPDATE bookings SET details=? WHERE id=?",
                       (json.dumps(details), booking_row["id"]))
        except Exception:
            pass


INSTALLMENT_PERCENT = float(os.getenv("INSTALLMENT_PERCENT", "30") or 30)   # pay-small-small policy


OFFICE_INFO = {
    "name": "JapaFly HQ (Brother'sTrust Travel)",
    "address": "Airport Residential Area, Accra (office also in Kumasi)",
    "hours": "Monday - Saturday, 8:00 AM - 8:00 PM",
    "phone": "+233 55 193 4922",
    "whatsapp": "https://wa.me/233551934922",
}


@router.post("/payments/installment")
def pay_installment(body: schemas.PaymentInitIn, db: sqlite3.Connection = Depends(get_db),
                    user=Depends(current_user)):
    """Pay small small: 30% now, balance within 4 working days. Confirmation
    issues automatically once the balance is paid."""
    page = _via_payment_page()
    if not page:
        _require_gateway()
    row = db.execute("SELECT * FROM bookings WHERE reference=? AND user_id=?",
                     (body.reference, user["id"])).fetchone()
    if row is None:
        raise HTTPException(404, "Booking not found")
    if row["status"] == "confirmed":
        return {"ok": True, "already_paid": True, "reference": row["reference"]}
    if row["status"] == "cancelled":
        raise HTTPException(400, "This booking was cancelled")
    details = json.loads(row["details"])
    if (details.get("installments") or {}).get("paid_first"):
        raise HTTPException(400, "First installment already paid - use Pay balance in My Bookings")
    first = max(1, round(row["amount"] * INSTALLMENT_PERCENT / 100))
    balance = round(row["amount"] - first)
    deadline = _working_deadline(4)
    details["installments"] = {"first": first, "balance": balance, "deadline": deadline,
                               "paid_first": True, "total": round(row["amount"])}
    db.execute("UPDATE bookings SET details=? WHERE id=?", (json.dumps(details), row["id"]))
    gateway_ref = "pay-" + make_reference("")[3:]
    db.execute("INSERT INTO payments (reference, booking_id, amount, status) VALUES (?,?,?,'pending')",
               (gateway_ref, row["id"], first))
    if page:
        return {"live": True, "authorization_url": page, "via": "payment_page",
                "first": first, "balance": balance, "deadline": deadline,
                "reference": row["reference"]}
    url = paystack.initialize(user["email"], first, gateway_ref,
                              f"{config.BASE_URL}/api/payments/callback", row["reference"])
    return {"live": True, "authorization_url": url, "first": first, "balance": balance,
            "deadline": deadline, "reference": row["reference"]}


@router.post("/payments/balance")
def pay_balance(body: schemas.PaymentConfirmIn, db: sqlite3.Connection = Depends(get_db),
                user=Depends(current_user)):
    """Settle the remaining balance of an installment booking."""
    page = _via_payment_page()
    if not page:
        _require_gateway()
    row = db.execute("SELECT * FROM bookings WHERE reference=? AND user_id=?",
                     (body.reference, user["id"])).fetchone()
    if row is None:
        raise HTTPException(404, "Booking not found")
    if row["status"] == "confirmed":
        return {"ok": True, "already_paid": True, "reference": row["reference"]}
    if row["status"] == "cancelled":
        raise HTTPException(400, "This booking was cancelled")
    due = round(row["amount"] - sum(a for (a,) in db.execute(
        "SELECT amount FROM payments WHERE booking_id=? AND status='paid'", (row["id"],))))
    if due <= 0:
        raise HTTPException(400, "Nothing left to pay")
    gateway_ref = "pay-" + make_reference("")[3:]
    db.execute("INSERT INTO payments (reference, booking_id, amount, status) VALUES (?,?,?,'pending')",
               (gateway_ref, row["id"], due))
    if page:
        return {"live": True, "authorization_url": page, "via": "payment_page",
                "due": due, "reference": row["reference"]}
    url = paystack.initialize(user["email"], due, gateway_ref,
                              f"{config.BASE_URL}/api/payments/callback", row["reference"])
    return {"live": True, "authorization_url": url, "due": due, "reference": row["reference"]}


@router.post("/payments/office")
def pay_at_office(body: schemas.PaymentInitIn, db: sqlite3.Connection = Depends(get_db),
                  user=Depends(current_user)):
    """Reserve a booking for in-person payment at the office. Stays 'pending'
    until an admin confirms the cash/POS payment in the dashboard."""
    row = db.execute("SELECT * FROM bookings WHERE reference=? AND user_id=?",
                     (body.reference, user["id"])).fetchone()
    if row is None:
        raise HTTPException(404, "Booking not found")
    if row["status"] == "confirmed":
        return {"ok": True, "already_paid": True, "reference": row["reference"]}
    if row["status"] == "cancelled":
        raise HTTPException(400, "This booking was cancelled")
    covered = db.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE booking_id=? AND status IN ('pending','paid')",
                         (row["id"],)).fetchone()[0]
    if covered < row["amount"]:
        db.execute("INSERT INTO payments (reference, booking_id, amount, status) VALUES (?,?,?,'pending')",
                   ("pay-" + make_reference("")[3:], row["id"], round(row["amount"] - covered)))
    db.execute("UPDATE payments SET method='Office' WHERE booking_id=? AND status='pending'", (row["id"],))
    notify(db, user["id"], "Booking reserved — pay at our office",
           f"Reference {row['reference']} is reserved. Visit us with your reference number to complete payment and get your ticket.")
    return {"ok": True, "reserved": True, "reference": row["reference"],
            "amount": row["amount"], "currency": row["currency"], "office": OFFICE_INFO}


@router.post("/payments/initialize")
def initialize(body: schemas.PaymentInitIn, db: sqlite3.Connection = Depends(get_db),
               user=Depends(current_user)):
    """Create (or reuse) the pending payment and return the Paystack checkout URL."""
    page = _via_payment_page()
    if not page:
        _require_gateway()
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
    if page:
        return {"authorization_url": page, "gateway_reference": gateway_ref,
                "amount": row["amount"], "currency": row["currency"], "live": True,
                "via": "payment_page"}
    try:
        url = paystack.initialize(user["email"], row["amount"], gateway_ref,
                                  f"{config.BASE_URL}/api/payments/callback", row["reference"])
        return {"authorization_url": url, "gateway_reference": gateway_ref,
                "amount": row["amount"], "currency": row["currency"], "live": True}
    except Exception as exc:
        raise HTTPException(502, f"Payment gateway error: {exc}")


@router.get("/payments/callback")
def callback(request: Request, reference: str = "", trxref: str = "",
             db: sqlite3.Connection = Depends(get_db)):
    """Browser return URL - verifies the transaction with Paystack before settling."""
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
    if ok and booking:
        _settle(db, pay["booking_id"], "Card")
    return RedirectResponse(f"/#/booking/{booking['reference'] if booking else reference}?paid={1 if ok else 0}")


@router.post("/payments/webhook")
async def webhook(request: Request, db: sqlite3.Connection = Depends(get_db)):
    """Server-to-server confirmation. Requires a valid Paystack HMAC signature.
    Payment-Page fallback transactions use Paystack-generated references and are
    never matched here - reconcile them manually in the admin dashboard."""
    _require_gateway()
    raw = await request.body()
    payload = json.loads(raw or b"{}")
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
