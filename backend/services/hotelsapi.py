# Live hotel provider (LiteAPI by Nuitee) — the hotel equivalent of Duffel:
# instant free sandbox key, 2M+ hotels, search -> book, no supplier contracts.
# Activates when LITEAPI_KEY is set; otherwise the demo catalog in seed.py is used.
import json
import os
import urllib.parse
import urllib.request
from datetime import date

import seed
from services import fx as _fx

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
            raw = r.read().decode()
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {"data": data}
    except urllib.error.HTTPError as exc:
        try:
            msg = json.loads(exc.read().decode()).get("message") or json.dumps(json.loads(exc.read().decode()))
        except Exception:
            msg = exc.reason
        raise HotelAPIError(f"LiteAPI {method} {path} failed ({exc.code}): {msg}")


# LiteAPI's /data/hotels accepts: countryCode, lat/lon, placeId, lastUpdatedAt,
# iata, or hotelIds (VERIFIED against the live API — "city" is NOT supported).
# We resolve the customer's city to a country code via our world dataset.
_COUNTRY_ISO = {
    "Ghana": "GH", "Nigeria": "NG", "Benin": "BJ", "Togo": "TG", "Burkina Faso": "BF",
    "Mali": "ML", "Senegal": "SN", "Ivory Coast": "CI", "Sierra Leone": "SL",
    "Liberia": "LR", "Guinea": "GN", "Guinea-Bissau": "GW", "Gambia": "GM",
    "Niger": "NE", "Chad": "TD", "Cameroon": "CM", "Congo": "CG", "DR Congo": "CD",
    "Kenya": "KE", "Uganda": "UG", "Tanzania": "TZ", "Rwanda": "RW", "Burundi": "BI",
    "Ethiopia": "ET", "Eritrea": "ER", "South Sudan": "SS", "Sudan": "SD",
    "South Africa": "ZA", "Botswana": "BW", "Namibia": "NA", "Angola": "AO",
    "Mozambique": "MZ", "Zambia": "ZM", "Zimbabwe": "ZW", "Malawi": "MW",
    "Madagascar": "MG", "Mauritius": "MU", "Seychelles": "SC",
    "Egypt": "EG", "Tunisia": "TN", "Algeria": "DZ", "Morocco": "MA", "Libya": "LY",
    "United Kingdom": "GB", "Ireland": "IE", "France": "FR", "Netherlands": "NL",
    "Germany": "DE", "Switzerland": "CH", "Spain": "ES", "Portugal": "PT",
    "Italy": "IT", "Austria": "AT", "Czech Republic": "CZ", "Hungary": "HU",
    "Poland": "PL", "Denmark": "DK", "Sweden": "SE", "Norway": "NO", "Finland": "FI",
    "Iceland": "IS", "Greece": "GR", "Türkiye": "TR", "Croatia": "HR",
    "Slovenia": "SI", "Slovakia": "SK", "Romania": "RO", "Bulgaria": "BG",
    "Albania": "AL", "North Macedonia": "MK", "Kosovo": "XK", "Estonia": "EE",
    "Latvia": "LV", "Lithuania": "LT", "Malta": "MT", "Serbia": "RS",
    "UAE": "AE", "Qatar": "QA", "Saudi Arabia": "SA", "Kuwait": "KW",
    "Bahrain": "BH", "Oman": "OM", "Jordan": "JO", "Lebanon": "LB", "Iraq": "IQ",
    "Singapore": "SG", "Malaysia": "MY", "Thailand": "TH", "Indonesia": "ID",
    "Philippines": "PH", "Vietnam": "VN", "Bangladesh": "BD", "Sri Lanka": "LK",
    "Pakistan": "PK", "India": "IN", "Hong Kong": "HK", "Taiwan": "TW",
    "China": "CN", "South Korea": "KR", "Japan": "JP",
    "USA": "US", "Canada": "CA", "Mexico": "MX", "Colombia": "CO", "Peru": "PE",
    "Chile": "CL", "Brazil": "BR", "Argentina": "AR", "Panama": "PA",
    "Costa Rica": "CR", "Cuba": "CU", "Dominican Republic": "DO", "Uruguay": "UY",
    "Australia": "AU", "New Zealand": "NZ", "Fiji": "FJ",
}


def _country_code_for(city: str):
    from services import world_data as wd
    q = (city or "").strip().lower()
    if not q:
        return None
    airports = wd.world_airports()
    for a in airports:
        if a["city"].lower() == q:
            return _COUNTRY_ISO.get(a["country"])
    for a in airports:
        if q in a["city"].lower():
            return _COUNTRY_ISO.get(a["country"])
    return None


def _static_hotels(city: str) -> list[dict]:
    if city not in _static_cache:
        cc = _country_code_for(city)
        if not cc:
            _static_cache[city] = []
        else:
            data = _req("GET", "/data/hotels", params={"countryCode": cc, "limit": 40})
            _static_cache[city] = data.get("data") or data.get("hotels") or []
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
    for item in (data.get("data") or []):
        hid = str(item.get("hotelId") or item.get("id"))
        meta = info.get(hid, {})
        nights = (checkout - checkin).days
        room_opts = []
        for rt in item.get("roomTypes", []):
            best = None
            for rate in (rt.get("rates") or []):
                if not rate:
                    continue
                retail = rate.get("retailRate") or {}
                total = retail.get("total") or [{}]
                amount = _fx.to_ghs(float((total[0] or {}).get("amount", 0) or 0),
                                    (total[0] or {}).get("currency", "GHS"))
                amount = amount * (1 + float(os.getenv("MARKUP_PERCENT", "0") or 0) / 100)
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


def cancel(confirmation_id: str) -> dict:
    """Cancel a live hotel reservation by its confirmation/booking id."""
    d = _req("POST", f"/bookings/{confirmation_id}/cancel", payload={})
    d = d.get("data") or {}
    return {"confirmation": confirmation_id, "cancelled": bool(d.get("bookingId") or d or confirmation_id)}


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
    d = data.get("data") or data
    return {"confirmation": d.get("bookingId") or d.get("id") or "", "status": d.get("status", "booked")}
