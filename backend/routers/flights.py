"""Flight search + booking."""
import sqlite3
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query

import schemas
import seed
from database import get_db
from deps import current_user, make_reference, notify, parse_date

router = APIRouter(tags=["flights"])


@router.get("/meta/flights")
def flight_meta():
    """Airports, cabins and route map for the search form."""
    return {
        "airports": [{"code": c, **a} for c, a in seed.AIRPORTS.items()],
        "cabins": [{"id": k, **v} for k, v in seed.CABINS.items()],
        "routes": [
            {"origin": o.split("-")[0], "dest": o.split("-")[1], "base": r["base"],
             "duration_min": r["duration"], "stops": r["stops"]}
            for o, r in seed.ROUTES.items()
        ],
    }


@router.get("/flights/search")
def search_flights(
    origin: str = Query(min_length=3, max_length=3),
    dest: str = Query(min_length=3, max_length=3),
    date: str = Query(...),
    cabin: str = Query("economy"),
):
    d = parse_date(date, "date")
    if d < date_type.today():
        raise HTTPException(400, "Departure date is in the past")
    if cabin not in seed.CABINS:
        raise HTTPException(400, "Unknown cabin class")
    flights = seed.flights_for(origin.upper(), dest.upper(), d, cabin)
    if not flights:
        raise HTTPException(404, "No flights on this route — pick another city pair")
    return {
        "origin": seed.AIRPORTS.get(origin.upper(), {}),
        "dest": seed.AIRPORTS.get(dest.upper(), {}),
        "date": d.isoformat(), "cabin": cabin,
        "flights": sorted(flights, key=lambda f: f["total"]),
    }


@router.post("/bookings/flight", status_code=201)
def book_flight(body: schemas.FlightBookingIn,
                db: sqlite3.Connection = Depends(get_db),
                user=Depends(current_user)):
    legs_out, total_fare, total_taxes = [], 0, 0
    for leg in body.legs:
        flight = seed.find_flight(leg.origin, leg.dest, leg.date, leg.flight_key, body.cabin)
        if flight is None:
            raise HTTPException(400, f"Flight {leg.flight_key} is no longer available — search again")
        legs_out.append(flight)
        total_fare += flight["fare"]
        total_taxes += flight["taxes"]
    mult = seed.pax_multiplier([p.model_dump() for p in body.passengers])
    fare = round(total_fare * mult)
    taxes = round(total_taxes * mult)
    service = seed.SERVICE_FEE_NGN
    amount = fare + taxes + service
    reference = make_reference("BTFL")
    details = {
        "trip_type": body.trip_type, "cabin": seed.CABINS[body.cabin]["label"],
        "legs": legs_out,
        "fare": fare, "taxes": taxes, "service_fee": service,
        "contact": {"email": body.contact_email, "phone": body.contact_phone},
    }
    travelers = [f"{p.title} {p.first_name} {p.last_name}" for p in body.passengers]
    db.execute(
        """INSERT INTO bookings (reference, user_id, type, status, amount, details, travelers)
           VALUES (?,?,?,?,?,?,?)""",
        (reference, user["id"], "flight", "pending", amount,
         __import__("json").dumps(details), __import__("json").dumps(travelers)))
    notify(db, user["id"], "Flight booking created",
           f"Reference {reference} — {len(body.passengers)} passenger(s), {body.legs[0].origin} to {body.legs[0].dest}. "
           f"Complete payment to confirm.")
    return {"reference": reference, "type": "flight", "status": "pending",
            "amount": amount, "currency": "NGN", "details": details,
            "travelers": travelers, "pay_path": f"/#/pay/{reference}"}
