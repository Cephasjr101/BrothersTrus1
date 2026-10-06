# Visa requirements, appointment slots and visa bookings.
import json
import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, HTTPException

import schemas
import seed
from database import get_db
from deps import current_user, make_reference, notify, parse_date

router = APIRouter(tags=["visa"])


@router.get("/meta/visa")
def visa_meta(db: sqlite3.Connection = Depends(get_db)):
    for c in seed.VISA_COUNTRIES:
        if c["category"] in ("embassy", "vfs") and c.get("centers"):
            seed.ensure_slots(db, c["code"], c["centers"][0], date.today())
    return {"countries": [{k: v for k, v in c.items()} for c in seed.VISA_COUNTRIES]}


@router.get("/visa/{code}/centers")
def visa_centers(code: str):
    c = seed.get_country(code)
    if c is None:
        raise HTTPException(404, "Unknown country")
    return {"country": c["name"], "category": c["category"],
            "centers": c.get("centers", []) if c["category"] in ("embassy", "vfs") else [],
            "no_appointment": c["category"] not in ("embassy", "vfs")}


@router.get("/visa/{code}/slots")
def visa_slots(code: str, center: str = "", db: sqlite3.Connection = Depends(get_db)):
    c = seed.get_country(code)
    if c is None:
        raise HTTPException(404, "Unknown country")
    if c["category"] not in ("embassy", "vfs"):
        return {"country": c["name"], "slots": [], "no_appointment": True}
    center = center or c["centers"][0]
    if center not in c["centers"]:
        raise HTTPException(400, "Unknown visa center")
    return {"country": c["name"], "center": center, "no_appointment": False,
            "slots": [s for s in seed.slots_for(db, c["code"], center, date.today()) if s["available"] > 0]}


@router.post("/bookings/visa", status_code=201)
def book_visa(body: schemas.VisaBookingIn,
              db: sqlite3.Connection = Depends(get_db),
              user=Depends(current_user)):
    c = seed.get_country(body.country_code)
    if c is None:
        raise HTTPException(404, "Unknown country")
    applicants = [a.model_dump() for a in body.applicants]

    if c["category"] in ("embassy", "vfs"):
        center = body.center or c["centers"][0]
        if center not in c["centers"]:
            raise HTTPException(400, "Unknown visa center")
        slot = db.execute(
            "SELECT * FROM visa_slots WHERE country=? AND center=? AND date=? AND time=?",
            (c["code"], center, body.date.isoformat(), body.time)).fetchone()
        if slot is None:
            seed.ensure_slots(db, c["code"], center, body.date)
            slot = db.execute(
                "SELECT * FROM visa_slots WHERE country=? AND center=? AND date=? AND time=?",
                (c["code"], center, body.date.isoformat(), body.time)).fetchone()
        if slot is None:
            raise HTTPException(400, "That appointment time is not offered")
        updated = db.execute(
            "UPDATE visa_slots SET booked = booked + ? WHERE id=? AND booked + ? <= capacity",
            (len(applicants), slot["id"], len(applicants)))
        if updated.rowcount == 0:
            raise HTTPException(409, "That slot just filled up — pick another time")
        center_out, date_out, time_out = center, body.date.isoformat(), body.time
    else:
        center_out, date_out, time_out = "", date.today().isoformat(), ""

    price = seed.price_visa(c["code"], len(applicants))
    reference = make_reference("BTVS")
    details = {
        "country_code": c["code"], "country": c["name"], "flag": c["flag"],
        "category": c["category"], "center": center_out, "date": date_out, "time": time_out,
        "processing": c["processing"], "validity": c["validity"], "stay": c["stay"],
        "price": price,
        "contact": {"email": body.contact_email, "phone": body.contact_phone},
    }
    travelers = [a["full_name"] for a in applicants]
    db.execute(
        "INSERT INTO bookings (reference, user_id, type, status, amount, details, travelers) VALUES (?,?,?,?,?,?,?)",
        (reference, user["id"], "visa", "pending", price["total"], json.dumps(details),
         json.dumps(travelers)))
    notify(db, user["id"], "Visa application created",
           f"Reference {reference} — {c['name']} visa for {len(applicants)} applicant(s). "
           f"Complete payment and our consultants will contact you within 24 hours.")
    return {"reference": reference, "type": "visa", "status": "pending",
            "amount": price["total"], "currency": "NGN", "details": details,
            "travelers": travelers, "pay_path": f"/#/pay/{reference}"}
