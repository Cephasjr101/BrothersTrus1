# Live hotel provider (LiteAPI by Nuitee) — the hotel equivalent of Duffel:
# instant free sandbox key, 2M+ hotels, search -> book, no supplier contracts.
# Activates when LITEAPI_KEY is set; otherwise the demo catalog in seed.py is used.
import json
import os
import urllib.parse
import urllib.request
from datetime import date

import seed

BASE = "https://api.liteapi.travel/v3.0"

_CITY_COVERS = {   # reuse the site's cover art per city
    "Lagos": "lagos-palm", "Abuja": "abuja-rock", "Accra": "accra-coast",
    "Dubai": "dubai-towers", "London": "london-river", "New York": "nyc-sky",
    "Paris": "paris-eiffel", "Nairobi": "nairobi-park", "Johannesburg": "abuja-city",
    "Kumasi": "accra-city", "Cape Town": "accra-coast",
}
_static_cache: dict[str, list] = {}


def configured() -> bool:
    return bool(os.getenv("LITEAPI_KEY"))


class HotelAPIError(RuntimeError):
    pass


def _req(method: str, path: str, params: dict | None = None, payload: dict | None = None) -> dict:
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, method=method, data=json.dumps(payload).encode() if payload else None,
                                 headers={"X-API-Key": os.getenv("LITEAPI_KEY", ""),
                                          "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            msg = json.loads(exc.read().decode()).get("message") or json.dumps(json.loads(exc.read().decode()))
        except Exception:
            msg = exc.reason
        raise HotelAPIError(f"LiteAPI {method} {path} failed ({exc.code}): {msg}")


def _static_hotels(city: str) -> list[dict]:
    if city not in _static_cache:
        data = _req("GET", "/data/hotels", params={"city": city, "limit": 40})
        _static_cache[city] = data.get("data", []) or data.get("hotels", []) or []
    return _static_cache[city]


def _stars(h: dict) -> int:
    raw = str(h.get("starRating") or h.get("category") or "").upper()
    for ch in raw:
        if ch.isdigit():
            return min(max(int(ch), 1), 5)
    return 4


def search(city: str, checkin: date, checkout: date, rooms: int, guests: int) -> dict:
    """Live hotel+rate search mapped onto the app's hotel card shape."""
    static = _static_hotels(city)
    ids = [h.get("id") or h.get("hotelId") for h in static]
    ids = [i for i in ids if i][:40]
    if not ids:
        return {"city": city.title(), "checkin": checkin.isoformat(), "checkout": checkout.isoformat(),
                "nights": (checkout - checkin).days, "rooms": rooms, "guests": guests, "hotels": []}
    occ = [{"adults": max(1, guests // rooms), "children": []} for _ in range(rooms)]
    data = _req("POST", "/hotels", payload={
        "hotelIds": ids, "occupancies": occ, "checkin": checkin.isoformat(),
        "checkout": checkout.isoformat(), "currency": "GHS", "guestNationality": "GH"})
    info = {str(h.get("id") or h.get("hotelId")): h for h in static}
    hotels = []
    for item in data.get("data", []):
        hid = str(item.get("hotelId") or item.get("id"))
        meta = info.get(hid, {})
        nights = (checkout - checkin).days
        room_opts = []
        for rt in item.get("roomTypes", []):
            best = None
            for rate in rt.get("rates", []):
                retail = (rate.get("retailRate") or {})
                total = (retail.get("total") or [{}])
                amount = float(total[0].get("amount", 0) or 0)
                if not retail.get("bookable", True) or amount <= 0:
                    continue
                if best is None or amount < best[0]:
                    best = (amount, rate, retail)
            if not best:
                continue
            amount, rate, retail = best
            perks = [p for p in (rt.get("amenities") or [])[:4]] or []
            if rate.get("boardName"):
                perks.insert(0, rate["boardName"])
            subtotal = round(amount) * nights * rooms
            vat = round(subtotal * seed.VAT)
            room_opts.append({
                "type": (rt.get("name") or "Room")[:60],
                "price": round(amount),
                "size": rt.get("view") or "",
                "occupancy": rt.get("maxOccupancy") or max(1, guests // rooms),
                "count": 5,
                "perks": perks or ["Free Wi-Fi"],
                "available": 5, "sold_out": False,
                "pricing": {"nights": nights, "rooms": rooms, "rate_per_night": round(amount),
                            "subtotal": subtotal, "vat": vat, "total": subtotal + vat},
                "rate_key": f"lite:{hid}:{rt.get('roomTypeId') or rt.get('id') or rt.get('name')}:{rate.get('rateId') or rate.get('id')}",
            })
        if room_opts:
            addr = meta.get("address") or {}
            hotels.append({
                "id": f"lite:{hid}", "name": meta.get("name") or meta.get("hotelName") or "Hotel",
                "city": city.title(), "country": (addr.get("country") or "") if isinstance(addr, dict) else "",
                "stars": _stars(meta), "rating": round(float(meta.get("reviewRating") or meta.get("rating") or 4.0), 1),
                "reviews": int(meta.get("reviewCount") or 0),
                "area": (addr.get("street") if isinstance(addr, dict) else None) or meta.get("neighborhood") or city.title(),
                "cover": _CITY_COVERS.get(city.title(), "lagos-sky"),
                "room_options": room_opts,
            })
    return {"city": city.title(), "checkin": checkin.isoformat(), "checkout": checkout.isoformat(),
            "nights": nights, "rooms": rooms, "guests": guests, "hotels": hotels}


def price(hotel_id: str, room_key: str, checkin: date, checkout: date, rooms: int, guests: int):
    """Re-price at booking time from a fresh search (never trust displayed prices)."""
    result = search(_city_for(hotel_id), checkin, checkout, rooms, guests)
    for h in result["hotels"]:
        for r in h["room_options"]:
            if r["rate_key"] == room_key:
                return r["pricing"]
    return None


def _city_for(hotel_id: str) -> str:
    # static cache holds the city from the original search; fallback to Accra
    for city, items in _static_cache.items():
        if any(str(h.get("id") or h.get("hotelId")) == hotel_id.replace("lite:", "") for h in items):
            return city
    return "Accra"


def book(hotel_id: str, room_key: str, checkin: str, checkout: str, rooms: int, guests: int,
         guest_name: str, contact: dict, travelers: list) -> dict:
    """Create the live reservation after customer payment. Sandbox = simulated."""
    parts = guest_name.split()
    payload = {
        "hold": False,
        "guest": {
            "firstName": parts[0] if parts else "Guest",
            "lastName": " ".join(parts[1:]) or "Traveler",
            "email": contact.get("email", ""), "phone": contact.get("phone", ""),
        },
        "payment": {"method": "wallet"},
        "rooms": [{"rateId": room_key.split(":")[-1], "occupancy": {"adults": max(1, guests // rooms), "children": []}}
                  for _ in range(rooms)],
        "checkin": checkin, "checkout": checkout,
    }
    data = _req("POST", "/bookings", payload=payload)
    d = data.get("data", data)
    return {"confirmation": d.get("bookingId") or d.get("id") or "", "status": d.get("status", "booked")}
