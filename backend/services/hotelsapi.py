"""LiteAPI (liteapi.travel) - live hotel search, price-check, booking.

Env: LITEAPI_KEY
Rates come from POST /v3.0/hotels/rates; hotel NAMES/photos/addresses do not -
they live in GET /v3.0/data/hotel. After a rates search we back-fill details
for any hotel that came back without them, so the UI never shows "Hotel".
"""
import os
import threading
import time
from datetime import date, datetime

import httpx

BASE = "https://api.liteapi.travel/v3.0"
KEY = os.getenv("LITEAPI_KEY", "")
CURRENCY = os.getenv("PAYMENTS_CURRENCY", "GHS")

_cache_lock = threading.Lock()
_hotel_cache: dict = {}


class LiteAPIError(RuntimeError):
    pass


def configured() -> bool:
    return bool(KEY)


def _H() -> dict:
    return {"X-API-Key": KEY, "Content-Type": "application/json"}


# ---------------------------------------------------------------- static data
def hotel_details(hotel_id: str, ttl: int = 86400) -> dict:
    """GET /v3.0/data/hotel - name, photos, address, star rating, etc."""
    if not hotel_id:
        return {}
    with _cache_lock:
        hit = _hotel_cache.get(hotel_id)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
    try:
        r = httpx.get(f"{BASE}/data/hotel", params={"hotelId": hotel_id},
                      headers=_H(), timeout=6)
        data = (r.json() or {}).get("data") or {}
    except Exception:
        data = {}
    with _cache_lock:
        _hotel_cache[hotel_id] = (time.time(), data)
    return data


def _merge_detail(h: dict, d: dict) -> None:
    if not d:
        return
    if h.get("name") in (None, "", "Hotel"):
        h["name"] = d.get("name") or h["name"]
    if not h.get("address") or h["address"] == h.get("city", ""):
        h["address"] = d.get("address") or h["address"]
    if not h.get("area") or h["area"] == h.get("city", ""):
        h["area"] = d.get("city") or h["area"]
    if d.get("country"):
        h["country"] = d["country"]
    h["stars"] = d.get("starRating") or h["stars"]
    h["rating"] = d.get("rating") or h["rating"]
    h["reviews"] = d.get("reviewCount") or h["reviews"]
    if not h.get("photo"):
        imgs = d.get("hotelImages") or []
        if imgs:
            h["photo"] = imgs[0].get("url", "")


def _fill_details(hotels: list) -> list:
    """Back-fill name/photo/address/stars from /data/hotel for hotels missing
    details. Hard deadline ~12s: whatever arrives in time merges, the rest
    keep placeholders - search NEVER blocks on details."""
    missing = [h for h in hotels if not h.get("_details_ok")]
    if not missing:
        return hotels
    missing = missing[:8]
    import time as _t
    from concurrent.futures import ThreadPoolExecutor, as_completed
    deadline = _t.time() + 12
    try:
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = {ex.submit(hotel_details, h["id"].replace("lite:", ""), ttl=86400): h for h in missing}
            for fut in as_completed(futs, timeout=12):
                h = futs[fut]
                try:
                    _merge_detail(h, fut.result(timeout=0.5))
                except Exception:
                    pass
                if _t.time() > deadline:
                    break
    except Exception:
        pass   # details are cosmetic - never break search over them
    for h in hotels:
        h.pop("_details_ok", None)
    return hotels


_search_cache: dict = {}


def _cache_get(key, ttl=600):
    import time as _t
    hit = _search_cache.get(key)
    if hit and _t.time() - hit[0] < ttl:
        return hit[1]
    return None


def _cache_put(key, value, keep=50):
    import time as _t
    if len(_search_cache) > keep:
        _search_cache.clear()
    _search_cache[key] = (_t.time(), value)


# ------------------------------------------------------------------- search --
def _fetch_hotels(kind: str, **params) -> dict:
    r = httpx.post(f"{BASE}/hotels/{kind}", headers=_H(),
                   json={k: v for k, v in params.items() if v is not None},
                   timeout=35)
    data = r.json()
    if r.status_code >= 400 or data.get("status", True) is False:
        raise LiteAPIError(f"{kind} failed: {data.get('error') or data.get('message') or r.text[:200]}")
    return data


def _pick_cheapest_rate(rt: dict) -> dict | None:
    """Cheapest bookable (all-required-boards-available) offer in a room type."""
    best = None
    for offer in (rt.get("offers") or []):
        if not offer.get("available", True):
            continue
        rr = offer.get("retailRate") or {}
        if rr.get("type") != "base":
            continue
        price = (rr.get("amount") or 0) + (rr.get("taxAmount") or 0)
        if best is None or price < best[0]:
            best = (price, offer)
    return best[1] if best else None


def _parse(data: dict, nights: int, city: str) -> dict:
    items = data.get("data") or []
    hotels = []
    for item in items:
        hid = item.get("hotelId") or item.get("id")
        if not hid:
            continue
        h = item.get("hotel") or item.get("hotelData") or {}
        gf = lambda *ks, d=None: next((h[k] for k in ks if h.get(k)), d)

        photos = gf("mainPhoto", "picture", "thumbnail", "heroImage")
        if not photos and isinstance(h.get("photos") or h.get("images"), list):
            first = (h.get("photos") or h.get("images"))[0]
            photos = (first or {}).get("url") if isinstance(first, dict) else first

        rts = [rt for rt in (item.get("roomTypes") or [])
               if rt.get("offers") and _pick_cheapest_rate(rt)]
        if not rts:
            continue

        rt0 = rts[0]
        offer0 = _pick_cheapest_rate(rt0)
        rr0 = offer0.get("retailRate") or {}
        per_night = round((rr0.get("amount") or 0) / max(nights, 1), 2)

        rating = gf("rating", "reviewRating", "guestRating", d=0) or 0
        try:
            rating = round(float(rating), 1)
        except Exception:
            rating = 0
        reviews = gf("reviewCount", "reviewsCount", "numReviews", d=0) or 0
        try:
            reviews = int(float(reviews))
        except Exception:
            reviews = 0

        addr = gf("address", "fullAddress", "locationAddress", d="") or ""
        if isinstance(addr, dict):
            addr = ", ".join(str(v) for v in addr.values() if v)
        area = gf("area", "neighbourhood", "neighborhood", "district", d="") or ""
        country = gf("country", d="") or ""
        if len(country) == 2:
            country = country.upper()
        stars = gf("starRating", "stars", "category", d=0) or 0
        try:
            stars = int(float(stars))
        except Exception:
            stars = 0

        # got real embedded hotel data? then skip the detail back-fill
        details_ok = bool(gf("name", "hotelName", "hotel_name"))

        rooms = []
        for rt in rts:
            offer = _pick_cheapest_rate(rt)
            rr = offer.get("retailRate") or {}
            amount = rr.get("amount") or 0
            tax = rr.get("taxAmount") or 0
            cancel = offer.get("cancelPolicyCode") or offer.get("cancellationPolicy") or ""
            if isinstance(cancel, dict):
                cancel = "refundable" if cancel.get("refundable") else "non-refundable"
            cancel = str(cancel).lower()
            refundable = "non" not in cancel and cancel != ""
            beds = rt.get("beds") or {}
            rooms.append({
                "pricing": {"nights": nights, "rooms": 1, "room_total": round(amount, 2),
                            "vat": round(tax, 2), "total": round(amount + tax, 2),
                            "currency": rr.get("currency") or CURRENCY},
                "type": rt.get("name") or rt.get("roomType") or "Room",
                "desc": rt.get("description") or "",
                "bed": beds if isinstance(beds, str) else
                       (f"{beds.get('type', '')} {beds.get('size', '')}".strip() or None),
                "meal": offer.get("mealPlan") or rt.get("mealPlan") or None,
                "price_per_night": round(amount / max(nights, 1), 2),
                "total": round(amount + tax, 2),
                "tax": round(tax, 2),
                "currency": rr.get("currency") or CURRENCY,
                "refundable": refundable,
                "cancellation": cancel,
                "available": bool(offer.get("available", True)),
                "perks": [],
                "occupancy": rt.get("maxAdults") or rt.get("adults") or 2,
                "price": round(amount / max(nights, 1), 2),
                "amenities": rt.get("amenities") or [],
                "adults": rt.get("maxAdults") or rt.get("adults") or 2,
                "rate_key": f"lite:{hid}:{offer.get('offerId')}",
                "offer_id": offer.get("offerId"),
            })

        room_only = min(r["price_per_night"] for r in rooms)
        total_min = min(r["total"] for r in rooms)

        hotels.append({
            "id": f"lite:{hid}",
            "name": gf("name", "hotelName", "hotel_name", d="Hotel"),
            "stars": stars,
            "rating": rating,
            "reviews": reviews,
            "address": addr or city.title(),
            "area": area or city.title(),
            "city": gf("city", d=city.title()) or city.title(),
            "country": country,
            "photo": photos or "",
            "cover": (city.strip().lower().split(",")[0].replace(" ", "-") + "-coast"),
            "amenities": [],
            "about": "",
            "phone": "",
            "email": "",
            "room_only": room_only,
            "total_min": total_min,
            "rooms": rooms,
            "room_options": rooms,
            "_details_ok": details_ok,
        })

    return {"hotels": _fill_details(hotels)}


# LiteAPI /hotels/rates only accepts countryCode, lat/lng, placeId,
# IATA or hotelIds - NOT free-text city names. Map known cities to
# coordinates; fall back to a country-wide search otherwise.
CITY_GEO = {
    "accra":        (5.6037, -0.1870, "GH"),
    "kumasi":       (6.6666, -1.6163, "GH"),
    "tamale":       (9.4034, -0.8393, "GH"),
    "lagos":        (6.5244, 3.3792, "NG"),
    "abuja":        (9.0820, 7.3983, "NG"),
    "nairobi":      (-1.2921, 36.8219, "KE"),
    "addis ababa":  (8.9806, 38.7578, "ET"),
    "dubai":        (25.2048, 55.2708, "AE"),
    "london":       (51.5074, -0.1278, "GB"),
    "new york":     (40.7128, -74.0060, "US"),
    "johannesburg": (-26.2041, 28.0473, "ZA"),
    "paris":        (48.8566, 2.3522, "FR"),
    "istanbul":     (41.0082, 28.9784, "TR"),
    "cairo":        (30.0444, 31.2357, "EG"),
}
COUNTRY_CODES = {
    "ghana": "GH", "nigeria": "NG", "kenya": "KE", "ethiopia": "ET",
    "uae": "AE", "dubai": "AE", "united arab emirates": "AE",
    "uk": "GB", "united kingdom": "GB", "london": "GB", "england": "GB",
    "usa": "US", "united states": "US", "new york": "US",
    "south africa": "ZA", "france": "FR", "paris": "FR",
    "turkey": "TR", "istanbul": "TR", "egypt": "EG", "cairo": "EG",
}


def _resolve_city(city: str) -> dict:
    """Map free-text input to params LiteAPI /hotels/rates accepts."""
    q = city.strip().lower()
    if q in CITY_GEO:
        lat, lng, cc = CITY_GEO[q]
        return {"latitude": lat, "longitude": lng, "countryCode": cc}
    if q in COUNTRY_CODES:
        return {"countryCode": COUNTRY_CODES[q]}
    if len(q) == 2 and q.isalpha():
        return {"countryCode": q.upper()}
    # "Accra, Ghana" / "paris france" style
    for sep in (",", " "):
        if sep in q:
            head = q.split(sep)[0].strip()
            if head in CITY_GEO:
                lat, lng, cc = CITY_GEO[head]
                return {"latitude": lat, "longitude": lng, "countryCode": cc}
    # last resort: country-wide scan, filtered client-side to the city name
    return {"countryCode": "", "cityName": city.strip()}



def _hotels_static(params: dict, limit: int = 60) -> list:
    """One call to POST /v3.0/hotels returns many hotels WITH names/photos."""
    body = {"limit": limit, "offset": 0}
    for k in ("latitude", "longitude", "countryCode", "cityName", "placeId"):
        if k in params:
            body[k] = params[k]
    if not any(k in body for k in ("latitude", "countryCode", "cityName", "placeId")):
        return []
    r = httpx.post(f"{BASE}/hotels", headers=_H(), json=body, timeout=20)
    if r.status_code in (404, 405):
        r = httpx.get(f"{BASE}/hotels", params=body, headers=_H(), timeout=20)
    data = r.json()
    if r.status_code >= 400:
        raise LiteAPIError(f"static hotels failed: {data.get('error') or data.get('name') or r.text[:150]}")
    return data.get("data") or []


def _merge_static(h: dict, st: dict) -> None:
    if h.get("name") in (None, "", "Hotel") and st.get("name"):
        h["name"] = st["name"]
    addr = st.get("address")
    if isinstance(addr, dict):
        line = ", ".join(str(v) for v in addr.values() if v)
    else:
        line = str(addr or "")
    if line and (not h.get("address") or h["address"] == h.get("city", "")):
        h["address"] = line
    if st.get("city") and (not h.get("area") or h["area"] == h.get("city", "")):
        h["area"] = st["city"]
    if st.get("country"):
        h["country"] = st["country"]
    h["stars"] = st.get("starRating") or h.get("stars")
    h["rating"] = st.get("rating") or h.get("rating")
    h["reviews"] = st.get("reviewCount") or h.get("reviews")
    if not h.get("photo"):
        img = st.get("mainPhoto") or {}
        url = img.get("url") if isinstance(img, dict) else img
        if not url and isinstance(st.get("hotelImages"), list) and st["hotelImages"]:
            first = st["hotelImages"][0] or {}
            url = first.get("url") if isinstance(first, dict) else first
        if url:
            h["photo"] = url

def search(city: str, checkin: date, checkout: date, rooms: int, guests: int) -> dict:
    key = (city.strip().lower(), checkin.isoformat(), checkout.isoformat(), rooms, guests)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    nights = (checkout - checkin).days
    params = _resolve_city(city)
    occupancies = [{"adults": guests, "children": [], "childrenAges": []} for _ in range(rooms)]
    base = {
        "checkin": checkin.isoformat(),
        "checkout": checkout.isoformat(),
        "currency": CURRENCY,
        "guestNationality": "GH",
        "occupancies": occupancies,
        "limit": 40,
        "maxRatesPerHotel": 3,
        "includeHotelData": True,
        "lastId": None,
        "timeout": 35,
    }
    if not params.get("countryCode") and "latitude" not in params:
        # unknown place: scan the whole country list is impossible without a
        # code - ask for a known city/country instead of a guaranteed 4000
        raise LiteAPIError(
            f"unknown location '{city}' - search a major city "
            f"({', '.join(sorted(CITY_GEO)[:8])}, ...) or a country name")
    try:
        data = _fetch_hotels("rates", **base, **params)
    except LiteAPIError:
        if params.get("countryCode") and ("latitude" in params or "cityName" in params):
            # narrow search failed ("no available properties") - widen to country
            data = _fetch_hotels("rates", **base,
                                 countryCode=params["countryCode"])
        else:
            raise
    result = _parse(data, nights, city)
    # bulk name/photo back-fill from the static hotels endpoint (one call)
    try:
        static = _hotels_static(params, limit=60)
        by_id = {str(s.get("id") or s.get("hotelId")): s for s in static}
        merged = 0
        for h in result["hotels"]:
            st = by_id.get(h["id"].replace("lite:", ""))
            if st:
                _merge_static(h, st)
                merged += 1
        print(f"[hotels] static merge {merged}/{len(result['hotels'])}", flush=True)
        if merged < max(1, len(result["hotels"]) // 3):
            _fill_details(result["hotels"])   # sparse merge -> per-hotel fallback
    except Exception as exc:
        print(f"[hotels] static fetch failed: {exc}", flush=True)
        _fill_details(result["hotels"])
    _cache_put(key, result)
    return result


def price(hotel_id: str, rate_key: str, checkin: date, checkout: date, rooms: int, guests: int) -> dict | None:
    """Re-price a specific offer at checkout time; None if gone."""
    hid = hotel_id.replace("lite:", "")
    occupancies = [{"adults": guests, "children": [], "childrenAges": []} for _ in range(rooms)]
    data = _fetch_hotels("rates", hotelIds=[hid], checkin=checkin.isoformat(),
                         checkout=checkout.isoformat(), currency=CURRENCY,
                         guestNationality="GH", occupancies=occupancies,
                         maxRatesPerHotel=3, timeout=35)
    target = None
    for item in (data.get("data") or []):
        if (item.get("hotelId") or item.get("id")) != hid:
            continue
        for rt in (item.get("roomTypes") or []):
            for offer in (rt.get("offers") or []):
                if offer.get("offerId") and str(offer.get("offerId")) in str(rate_key):
                    target = offer
                    break
            if target:
                break
        if target:
            break
    if not target:
        return None
    rr = target.get("retailRate") or {}
    nights = (checkout - checkin).days
    amount = rr.get("amount") or 0
    tax = rr.get("taxAmount") or 0
    return {"nights": nights, "rooms": rooms, "room_total": round(amount, 2),
            "tax": round(tax, 2), "total": round(amount + tax, 2),
            "currency": rr.get("currency") or CURRENCY}


def prebook(rate_key: str):
    hid, offer = str(rate_key).split(":")[1], str(rate_key).split(":")[2]
    r = httpx.post(f"{BASE}/rates/prebook", headers=_H(),
                   json={"offerId": offer, "useCache": True}, timeout=25)
    data = r.json()
    if r.status_code >= 400 or not data.get("data"):
        raise LiteAPIError(data.get("error") or data.get("message") or "prebook failed")
    return data["data"]


def book(hotel_id: str, rate_key: str, checkin: date, checkout: date,
         rooms: int, guests: int, guest_name: str, contact: dict, travelers=None) -> dict:
    """Create a LiteAPI booking from a rate key; returns confirmation details."""
    pre = prebook(rate_key)
    hold = pre.get("hold") or {}
    price = pre.get("price") or {}
    bookable = hold.get("bookableUntil") or hold.get("expiresAt") or hold.get("validUntil")
    if bookable:
        try:
            expiry = datetime.fromisoformat(str(bookable).replace("Z", "+00:00"))
            if expiry.timestamp() < time.time():
                raise LiteAPIError("Rate hold expired - re-price and try again")
        except ValueError:
            pass
    amount = price.get("total") or price.get("amount") or 0
    customer = {"email": (contact or {}).get("email", "guest@japafly.com"),
                "phone": (contact or {}).get("phone", "+233551934922")}
    guests_payload = [{"occupancyNumber": 1, "firstName": (guest_name or "Guest").split()[0],
                       "lastName": " ".join((guest_name or "Guest").split()[1:]) or "Guest",
                       "email": customer["email"]}]
    r = httpx.post(f"{BASE}/booking", headers=_H(), json={
        "offerId": str(rate_key).split(":")[2], "useCache": True,
        "checkin": checkin.isoformat(), "checkout": checkout.isoformat(),
        "customer": customer, "guests": guests_payload,
    }, timeout=30)
    data = r.json()
    if r.status_code >= 400 or not data.get("data"):
        raise LiteAPIError(data.get("error") or data.get("message") or "booking failed")
    d = data["data"]
    hid = hotel_id.replace("lite:", "")
    det = hotel_details(hid)
    return {
        "booking_id": d.get("bookingId") or d.get("id"),
        "confirmation": d.get("confirmation") or d.get("confirmationNumber") or "",
        "status": d.get("status") or "confirmed",
        "amount": amount or d.get("total") or 0,
        "hotel": det.get("name") or hotel_id,
        "checkin": checkin.isoformat(), "checkout": checkout.isoformat(),
    }
