# Live hotel provider (LiteAPI by Nuitee) — hotel equivalent of Duffel.
# Endpoints per official v3.0 docs:
#   search   POST https://api.liteapi.travel/v3.0/hotels/rates
#   prebook  POST https://book.liteapi.travel/v3.0/rates/prebook   (offerId -> prebookId)
#   book     POST https://book.liteapi.travel/v3.0/rates/book      (prebookId -> booking)
#   cancel   PUT  https://api.liteapi.travel/v3.0/bookings/{id}
# Search supports cityName+countryCode directly and includes hotel data inline.
import json
import os
import urllib.parse
import urllib.request
from datetime import date

import seed
from services import fx as _fx

API_HOST = "https://api.liteapi.travel"
BOOK_HOST = "https://book.liteapi.travel"

_offer_city: dict[str, str] = {}


def configured() -> bool:
    return bool(os.getenv("LITEAPI_KEY"))


class HotelAPIError(RuntimeError):
    pass


def _req(method: str, path: str, payload: dict | None = None,
         params: dict | None = None, host: str = API_HOST) -> dict:
    url = host + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, method=method, data=json.dumps(payload).encode() if payload is not None else None,
                                 headers={"X-API-Key": os.getenv("LITEAPI_KEY", ""),
                                          "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=35) as r:
            raw = r.read().decode()
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {"data": data}
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode())
            msg = body.get("message") or (body.get("error") or {}).get("message") or json.dumps(body)[:160]
        except Exception:
            msg = exc.reason
        raise HotelAPIError(f"LiteAPI {method} {path} failed ({exc.code}): {msg}")


# ------------------------------------------------------------------ helpers
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


def _stars(h) -> int:
    raw = str(h.get("starRating") or h.get("category") or h.get("stars") or "").upper()
    for ch in raw:
        if ch.isdigit():
            return min(max(int(ch), 1), 5)
    return 4


def _covers(city: str) -> str:
    return {"Lagos": "lagos-palm", "Abuja": "abuja-rock", "Accra": "accra-coast",
            "Dubai": "dubai-towers", "London": "london-river", "New York": "nyc-sky",
            "Paris": "paris-eiffel", "Nairobi": "nairobi-park"}.get(city.title(), "lagos-sky")


def _markup(amount: float) -> float:
    return amount * (1 + float(os.getenv("MARKUP_PERCENT", "0") or 0) / 100)


# ------------------------------------------------------------------ search
def _hotel_photo(h: dict, item: dict) -> str:
    """First real photo URL from LiteAPI hotel data (field names vary by shape)."""
    for src in (h or {}, item or {}):
        for key in ("mainPhoto", "picture", "thumbnail", "heroImage"):
            u = src.get(key)
            if isinstance(u, str) and u.startswith("http"):
                return u
        for key in ("photos", "images", "gallery", "pictures"):
            arr = src.get(key)
            if isinstance(arr, list) and arr:
                first = arr[0]
                u = first.get("url") or first.get("link") if isinstance(first, dict) else first
                if isinstance(u, str) and u.startswith("http"):
                    return u
    return ""


def search(city: str, checkin: date, checkout: date, rooms: int, guests: int) -> dict:
    """Live rate search by city — hotel data comes inline when searching by filters."""
    nights = (checkout - checkin).days
    cc = _country_code_for(city)
    body = {
        "checkin": checkin.isoformat(), "checkout": checkout.isoformat(),
        "currency": "GHS", "guestNationality": "GH",
        "occupancies": [{"adults": max(1, guests // rooms), "children": []} for _ in range(rooms)],
        "limit": 40, "maxRatesPerHotel": 3, "includeHotelData": True,
    }
    if cc:
        body["countryCode"] = cc
        body["cityName"] = city
    else:
        body["aiSearch"] = f"hotels in {city}"
    data = _req("POST", "/v3.0/hotels/rates", payload=body)

    hotels = []
    for item in data.get("data") or []:
        hid = str(item.get("hotelId") or "")
        h = item.get("hotel") or item.get("hotelData") or {}
        if not isinstance(h, dict):
            h = {}
        if not hid and h.get("id"):
            hid = str(h["id"])
        if not hid:
            continue

        def gf(*keys):
            """Read a hotel field from the nested hotel object OR the flattened item."""
            for k in keys:
                v = h.get(k)
                if v in (None, "", {}):
                    v = item.get(k)
                if v not in (None, "", {}):
                    return v
            return None
        room_opts = []
        for rt in item.get("roomTypes") or []:
            best = None
            for rate in rt.get("rates") or []:
                if not rate:
                    continue
                retail = rate.get("retailRate") or {}
                tot = retail.get("total") or [{}]
                amt = float((tot[0] or {}).get("amount", 0) or 0)
                cur = (tot[0] or {}).get("currency", "GHS")
                if amt <= 0:
                    continue
                if best is None or amt < best[0]:
                    best = (amt, cur, rate, retail)
            if not best:
                continue
            amt, cur, rate, retail = best
            amt_ghs = _markup(_fx.to_ghs(amt, cur))
            per_night = round(amt_ghs / nights)
            subtotal = round(amt_ghs)
            vat = round(subtotal * seed.VAT)
            offer_id = rt.get("offerId") or rate.get("offerId") or ""
            if offer_id:
                _offer_city[offer_id] = city
            perks = []
            if rate.get("boardName") or rt.get("boardType"):
                perks.append(rate.get("boardName") or rt.get("boardType"))
            for a in (rt.get("amenities") or [])[:3]:
                perks.append(a if isinstance(a, str) else (a or {}).get("name", ""))
            room_opts.append({
                "type": (rt.get("name") or rate.get("roomName") or rate.get("name") or "Room")[:60],
                "price": per_night, "size": rt.get("view") or "",
                "occupancy": rt.get("maxOccupancy") or max(1, guests // rooms),
                "count": 5, "perks": [p for p in perks if p] or ["Free Wi-Fi"],
                "available": 5, "sold_out": False,
                "pricing": {"nights": nights, "rooms": rooms, "rate_per_night": per_night,
                            "subtotal": subtotal, "vat": vat, "total": subtotal + vat},
                "rate_key": f"lite:{hid}:{offer_id}" if offer_id else "",
            })
        room_opts = [r for r in room_opts if r["rate_key"]]
        if room_opts:
            addr = gf("address") or {}
            if not isinstance(addr, dict):
                addr = {}
            name = gf("name", "hotelName", "hotel_name") or "Hotel"
            stars = gf("starRating", "stars", "category")
            rating = gf("rating", "reviewRating", "reviewScore", "guestRating", "reviewScoreLocalized")
            reviews = gf("reviewCount", "reviewsCount", "numberOfReviews", "reviews")
            hotels.append({
                "id": f"lite:{hid}",
                "name": name,
                "city": city.title(), "country": cc or "",
                "stars": _stars({"starRating": stars} if stars else {}),
                "rating": round(float(rating or 4.0), 1),
                "reviews": int(reviews or 0),
                "area": addr.get("city") or addr.get("street") or city.title(),
                "cover": _covers(city),
                "photo": _hotel_photo(h, item),
                "room_options": room_opts,
            })
    return {"city": city.title(), "checkin": checkin.isoformat(), "checkout": checkout.isoformat(),
            "nights": nights, "rooms": rooms, "guests": guests, "hotels": hotels}


# ------------------------------------------------------------------ revalidate / book / cancel
def price(hotel_id: str, room_key: str, checkin: date, checkout: date, rooms: int, guests: int):
    """Re-price at checkout from a fresh search — the offer disappears once sold/expired."""
    offer_id = room_key.split(":")[-1]
    city = _offer_city.get(offer_id) or hotel_id.replace("lite:", "")
    try:
        result = search(city if isinstance(city, str) else "Accra", checkin, checkout, rooms, guests)
    except HotelAPIError:
        return None
    for h in result["hotels"]:
        for r in h["room_options"]:
            if r["rate_key"] == room_key:
                return r["pricing"]
    return None


def book(hotel_id: str, room_key: str, checkin: str, checkout: str, rooms: int, guests: int,
         guest_name: str, contact: dict, travelers: list) -> dict:
    """Prebook the offer, then confirm — the real reservation. Sandbox = simulated."""
    offer_id = room_key.split(":")[-1]
    pre = _req("POST", "/v3.0/rates/prebook", payload={"offerId": offer_id, "usePaymentSdk": False},
               host=BOOK_HOST)
    prebook_id = (pre.get("data") or {}).get("prebookId") or (pre.get("data") or {}).get("id")
    if not prebook_id:
        raise HotelAPIError(f"Prebook returned no prebookId: {str(pre)[:160]}")
    parts = guest_name.split()
    payload = {
        "prebookId": prebook_id,
        "guest": {"firstName": parts[0] if parts else "Guest",
                  "lastName": " ".join(parts[1:]) or "Traveler",
                  "email": contact.get("email", ""), "phone": contact.get("phone", "")},
        "payment": {"method": "wallet"},
    }
    b = _req("POST", "/v3.0/rates/book", payload=payload, host=BOOK_HOST)
    d = b.get("data") or {}
    return {"confirmation": d.get("bookingId") or d.get("id") or prebook_id,
            "status": d.get("status", "booked")}


def cancel(confirmation_id: str) -> dict:
    """Cancel a live hotel reservation."""
    _req("PUT", f"/v3.0/bookings/{confirmation_id}", payload={})
    return {"confirmation": confirmation_id, "cancelled": True}
