"""Hotel search + booking."""
import json
import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

import schemas
import seed
from database import get_db
from deps import current_user, make_reference, notify, parse_date

router = APIRouter(tags=["hotels"])


@router.get("/meta/hotels")
def hotel_meta():
    return {"cities": seed.HOTEL_CITIES, "hotels": len(seed.HOTELS)}


@router.get("/hotels/search")
def search_hotels(
    city: str,
    checkin: str = Query(...),
    checkout: str = Query(...),
    guests: int = Query(2, ge=1, le=10),
    rooms: int = Query(1, ge=1, le=5),
    db: sqlite3.Connection = Depends(get_db),
):
    ci, co = parse_date(checkin, "checkin"), parse_date(checkout, "checkout")
    if ci < date.today():
        raise HTTPException(400, "Check-in date is in the past")
    if co <= ci:
        raise HTTPException(400, "Check-out must be after check-in")
    nights = (co - ci).days
    out = []
    for h in seed.HOTELS:
        if h["city"].lower() != city.lower():
            continue
        room_opts = []
        for r in h["rooms"]:
            if r["occupancy"] * rooms < guests:
                continue
            avail = seed.hotel_rooms_available(db, h["id"], r["type"], ci, co)
            price = seed.price_hotel(h["id"], r["type"], ci, co, rooms)
            room_opts.append({**r, "available": avail, "pricing": price, "sold_out": avail < rooms})
        if room_opts:
            out.append({**h, "room_options": room_opts})
    if not out:
        raise HTTPException(404, f"No available hotels in {city} for those dates")
    return {"city": city.title(), "checkin": ci.isoformat(), "checkout": co.isoformat(),
            "nights": nights, "rooms": rooms, "guests": guests, "hotels": out}


@router.post("/bookings/hotel", status_code=201)
def book_hotel(body: schemas.HotelBookingIn,
               db: sqlite3.Connection = Depends(get_db),
               user=Depends(current_user)):
    hotel = seed.get_hotel(body.hotel_id)
    if hotel is None:
        raise HTTPException(404, "Hotel not found")
    room = next((r for r in hotel["rooms"] if r["type"] == body.room_type), None)
    if room is None:
        raise HTTPException(400, "Unknown room type for this hotel")
    avail = seed.hotel_rooms_available(db, hotel["id"], room["type"], body.checkin, body.checkout)
    if avail < body.rooms:
        raise HTTPException(409, f"Only {avail} room(s) left for those dates — try another room or date")
    price = seed.price_hotel(hotel["id"], room["type"], body.checkin, body.checkout, body.rooms)
    reference = make_reference("BTHT")
    details = {
        "hotel_id": hotel["id"], "hotel_name": hotel["name"], "city": hotel["city"],
        "country": hotel["country"], "stars": hotel["stars"], "area": hotel["area"],
        "room_type": room["type"], "checkin": body.checkin.isoformat(),
        "checkout": body.checkout.isoformat(), "rooms": body.rooms, "guests": body.guests,
        "pricing": price, "special_requests": body.special_requests,
        "contact": {"email": body.contact_email, "phone": body.contact_phone},
    }
    db.execute(
        """INSERT INTO bookings (reference, user_id, type, status, amount, details, travelers)
           VALUES (?,?,?,?,?,?,?)""",
        (reference, user["id"], "hotel", "pending", price["total"], json.dumps(details),
         json.dumps([body.guest_name])))
    notify(db, user["id"], "Hotel reservation created",
           f"Reference {reference} — {hotel['name']}, {price['nights']} night(s), {body.rooms} room(s). Complete payment to confirm.")
    return {"reference": reference, "type": "hotel", "status": "pending",
            "amount": price["total"], "currency": "NGN", "details": details,
            "travelers": [body.guest_name], "pay_path": f"/#/pay/{reference}"}
