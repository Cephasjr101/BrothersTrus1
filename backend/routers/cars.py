"""Car rental search + booking."""
import json
import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

import schemas
import seed
from database import get_db
from deps import current_user, make_reference, notify, parse_date

router = APIRouter(tags=["cars"])


@router.get("/meta/cars")
def car_meta():
    return {
        "cities": [{"city": c, **v} for c, v in seed.CAR_CITIES.items()],
        "categories": [{**c, "features": f"{c['seats']} seats · {c['bags']} bags · {c['transmission']}"}
                       for c in seed.CAR_CATEGORIES],
        "suppliers": seed.CAR_SUPPLIERS,
    }


@router.get("/cars/search")
def search_cars(
    city: str,
    pickup_date: str = Query(...),
    return_date: str = Query(...),
    db: sqlite3.Connection = Depends(get_db),
):
    pu, rt = parse_date(pickup_date, "pickup_date"), parse_date(return_date, "return_date")
    if pu < date.today():
        raise HTTPException(400, "Pickup date is in the past")
    if rt <= pu:
        raise HTTPException(400, "Return date must be after pickup")
    if city not in seed.CAR_CITIES:
        raise HTTPException(404, f"We don't rent cars in {city} yet")
    days = (rt - pu).days
    out = []
    for cat in seed.CAR_CATEGORIES:
        avail = seed.cars_available(db, city, cat["code"], pu, rt)
        price = seed.price_car(city, cat["code"], pu, rt)
        out.append({**cat, "daily_rate": price["daily_rate"], "pricing": price,
                    "available": avail, "sold_out": avail < 1})
    supplier_i = int(abs(hash(f"{city}{pu.isoformat()}")) % len(seed.CAR_SUPPLIERS))
    return {"city": city, "pickup_date": pu.isoformat(), "return_date": rt.isoformat(),
            "days": days, "supplier": seed.CAR_SUPPLIERS[supplier_i], "cars": out}


@router.post("/bookings/car", status_code=201)
def book_car(body: schemas.CarBookingIn,
             db: sqlite3.Connection = Depends(get_db),
             user=Depends(current_user)):
    if body.city not in seed.CAR_CITIES:
        raise HTTPException(404, f"We don't rent cars in {body.city} yet")
    cat = next((c for c in seed.CAR_CATEGORIES if c["code"] == body.category), None)
    if cat is None:
        raise HTTPException(400, "Unknown car category")
    avail = seed.cars_available(db, body.city, cat["code"], body.pickup_date, body.return_date)
    if avail < 1:
        raise HTTPException(409, "No vehicles left in this class for those dates")
    price = seed.price_car(body.city, cat["code"], body.pickup_date, body.return_date)
    reference = make_reference("BTCR")
    details = {
        "city": body.city, "category": cat["code"], "category_name": cat["name"],
        "examples": cat["examples"], "pickup_date": body.pickup_date.isoformat(),
        "return_date": body.return_date.isoformat(), "pickup_location": body.pickup_location,
        "driver_age": body.driver_age, "pricing": price,
        "contact": {"email": body.contact_email, "phone": body.contact_phone},
    }
    db.execute(
        """INSERT INTO bookings (reference, user_id, type, status, amount, details, travelers)
           VALUES (?,?,?,?,?,?,?)""",
        (reference, user["id"], "car", "pending", price["total"], json.dumps(details),
         json.dumps([body.driver_name])))
    notify(db, user["id"], "Car booking created",
           f"Reference {reference} — {cat['name']} in {body.city} for {price['days']} day(s). Complete payment to confirm.")
    return {"reference": reference, "type": "car", "status": "pending",
            "amount": price["total"], "currency": "NGN", "details": details,
            "travelers": [body.driver_name], "pay_path": f"/#/pay/{reference}"}
