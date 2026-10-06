# My bookings, booking detail, cancellation, notifications.
import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from database import get_db
from deps import current_user
from services.notify import send_notification

router = APIRouter(tags=["bookings"])

REFUND_RATES = {"flight": 0.80, "hotel": 0.90, "car": 0.85, "visa": 0.90}


def _booking_out(row: sqlite3.Row) -> dict:
    return {
        "reference": row["reference"], "type": row["type"], "status": row["status"],
        "amount": row["amount"], "currency": row["currency"],
        "details": json.loads(row["details"]), "travelers": json.loads(row["travelers"]),
        "refund_amount": row["refund_amount"],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


def get_booking_row(db: sqlite3.Connection, reference: str, user_id: int) -> sqlite3.Row:
    row = db.execute("SELECT * FROM bookings WHERE reference = ? AND user_id = ?",
                     (reference, user_id)).fetchone()
    if row is None:
        raise HTTPException(404, "Booking not found")
    return row


@router.get("/bookings/mine")
def my_bookings(db: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    rows = db.execute(
        "SELECT * FROM bookings WHERE user_id = ? ORDER BY created_at DESC LIMIT 100",
        (user["id"],)).fetchall()
    return [_booking_out(r) for r in rows]


@router.get("/bookings/{reference}")
def booking_detail(reference: str, db: sqlite3.Connection = Depends(get_db),
                   user=Depends(current_user)):
    return _booking_out(get_booking_row(db, reference, user["id"]))


@router.post("/bookings/{reference}/cancel")
def cancel_booking(reference: str, db: sqlite3.Connection = Depends(get_db),
                   user=Depends(current_user)):
    row = get_booking_row(db, reference, user["id"])
    if row["status"] == "cancelled":
        raise HTTPException(400, "Booking is already cancelled")
    if row["status"] == "completed":
        raise HTTPException(400, "Completed bookings cannot be cancelled online")
    refund = round(row["amount"] * REFUND_RATES.get(row["type"], 0.9))
    db.execute(
        "UPDATE bookings SET status='cancelled', refund_amount=?, updated_at=datetime('now') WHERE id=?",
        (refund, row["id"]))
    # free up a visa slot if one was reserved
    details = json.loads(row["details"])
    if row["type"] == "visa" and details.get("center") and details.get("date"):
        db.execute(
            "UPDATE visa_slots SET booked = MAX(booked - ?, 0) WHERE country=? AND center=? AND date=? AND time=?",
            (len(json.loads(row["travelers"])), details.get("country_code", ""),
             details["center"], details["date"], details.get("time", "")))
    db.execute(
        "UPDATE payments SET status='refunded' WHERE booking_id=? AND status IN ('pending','paid')",
        (row["id"],))
    c = details.get("contact") or {}
    send_notification(db, user["id"], "Booking cancelled",
        f"Reference {reference} was cancelled. Refund of NGN {refund:,.0f} is processed to your original payment method within 5-7 working days.",
        email=c.get("email", ""), phone=c.get("phone", ""))
    return {"ok": True, "status": "cancelled", "refund_amount": refund}


@router.get("/notifications")
def notifications(db: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    rows = db.execute(
        "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 30",
        (user["id"],)).fetchall()
    return [{"id": r["id"], "title": r["title"], "body": r["body"],
             "read": r["read_at"] is not None, "created_at": r["created_at"]} for r in rows]


@router.post("/notifications/read")
def mark_read(db: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    db.execute("UPDATE notifications SET read_at=datetime('now') WHERE user_id=? AND read_at IS NULL",
               (user["id"],))
    return {"ok": True}
