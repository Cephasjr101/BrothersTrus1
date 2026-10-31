"""Partner hotels - properties JapaFly sells directly (no LiteAPI).

These are merged at the TOP of hotel search results for their city, tagged
"partner": true, and book through the normal pending-booking + Paystack flow.

To add a hotel: copy a block below, change the fields, keep the shape.
  - id MUST start with "partner:" and be unique
  - rate_key per room = "partner:<slug>:<room type>"
  - photo: external URL or a file in frontend/assets ("/assets/our-hotel.jpg")
  - price_per_night/total are per ROOM for the whole stay's nights handled
    at booking time (see routers/hotels.py partner branch)
"""
import os

CURRENCY = os.getenv("PAYMENTS_CURRENCY", "GHS")


def _hotel(slug, name, city, area, country, stars, photo, address,
           rating, reviews, rooms):
    return {
        "id": f"partner:{slug}",
        "name": name,
        "stars": stars,
        "rating": rating,
        "reviews": reviews,
        "address": address,
        "area": area,
        "city": city,
        "country": country,
        "photo": photo,
        "cover": slug + "-cover",
        "partner": True,
        "room_only": min(r["price_per_night"] for r in rooms),
        "total_min": min(r["total"] for r in rooms),
        "rooms": rooms,
        "room_options": rooms,
    }


def _room(room_type, desc, bed, meal, per_night, occupancy=2):
    return {
        "type": room_type,
        "desc": desc,
        "bed": bed,
        "meal": meal,
        "price_per_night": per_night,
        "total": per_night,          # recomputed for actual nights at booking
        "tax": 0,
        "currency": CURRENCY,
        "refundable": True,
        "cancellation": "free cancellation up to 48h before check-in",
        "available": True,           # own inventory - always sellable
        "amenities": [],
        "adults": occupancy,
        "rate_key": "",              # set by _hotel() wrapper below
        "offer_id": None,
    }


# ---------------------------------------------------------------- the hotels --
PARTNER_HOTELS = [
    _hotel(
        slug="japafly-suites-accra",
        name="JapaFly Suites (Airport Residential)",
        city="Accra", area="Airport Residential Area", country="GH",
        stars=4,
        photo="",                     # e.g. "/assets/japafly-suites.jpg"
        address="Airport Residential Area, Accra",
        rating=4.6, reviews=132,
        rooms=[
            _room("Standard Room", "Comfortable double room", "Queen bed", "Breakfast included", 850),
            _room("Executive Suite", "Larger suite with sitting area", "King bed", "Breakfast + airport pickup", 1450),
        ],
    ),
    _hotel(
        slug="brotherstrust-lodge-kumasi",
        name="Brother'sTrust Lodge Kumasi",
        city="Kumasi", area="Adum", country="GH",
        stars=3,
        photo="",
        address="Adum, Kumasi",
        rating=4.2, reviews=58,
        rooms=[
            _room("Deluxe Room", "Spacious room, city view", "Queen bed", "Room only", 520),
        ],
    ),
]

# fill in rate_key per room now that slugs are known
for _h in PARTNER_HOTELS:
    _slug = _h["id"].split(":", 1)[1]
    for _r in _h["rooms"]:
        _r["rate_key"] = f"partner:{_slug}:{_r['type']}"


def for_city(city: str) -> list:
    """Partner hotels matching a search city (name/area match)."""
    c = city.strip().lower()
    return [h for h in PARTNER_HOTELS
            if c in (h["city"] + " " + h["area"]).lower()]


def get(hotel_id: str):
    hid = hotel_id.replace("partner:", "")
    return next((h for h in PARTNER_HOTELS if h["id"].split(":", 1)[1] == hid), None)
