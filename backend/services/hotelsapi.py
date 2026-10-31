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
                      headers=_H(), timeout=8)
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
    """Back-fill name/photo/address/stars from /data/hotel for any hotel
    whose details were missing from the rates response. Runs in parallel
    and is capped so search latency stays acceptable."""
    missing = [h for h in hotels if not h.get("_details_ok")]
    if not missing:
        return hotels
    missing = missing[:16]
    from concurrent.futures import ThreadPoolExecutor
    try:
        with ThreadPoolExecutor(max_workers=8) as ex:
            details = list(ex.map(lambda h: hotel_details(h["id"].replace("lite:", ""), ttl=86400), missing))
        for h, d in zip(missing, details):
            _merge_detail(h, d)
    except Exception:
        pass   # details are cosmetic - never break search over them
    for h in hotels:
        h.pop("_details_ok", None)
    return hotels


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
            "room_only": room_only,
            "total_min": total_min,
            "rooms": rooms,
            "room_options": rooms,
            "_details_ok": details_ok,
        })

    return {"hotels": _fill_details(hotels)}


def _resolve_city(city: str) -> dict:
    """Map a free-text city to LiteAPI search parameters."""
    q = city.strip()
    params = {"cityName": q}
    if "," in q:
        city_part, country_part = [p.strip() for p in q.split(",", 1)]
        params["cityName"] = city_part
        params["countryCode"] = country_part[:2].upper()
    for sep in (" ", "-", "/"):
        if sep in q:
            parts = [p for p in q.split(sep) if p]
            if len(parts) >= 2 and all(p.isalpha() for p in parts[:2]):
                params["cityName"] = " ".join(parts[:2])
                break
    if len(q) == 2 and q.isalpha():
        params = {"countryCode": q.upper()}
    return params


def search(city: str, checkin: date, checkout: date, rooms: int, guests: int) -> dict:
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
    try:
        data = _fetch_hotels("rates", **base, **params)
    except LiteAPIError:
        # destination-based searches can fail ("no available properties");
        # country-wide rate scans still give bookable results nearby
        if "cityName" in params and params.get("countryCode"):
            params = {"countryCode": params["countryCode"]}
            data = _fetch_hotels("rates", **base, **params)
        else:
            raise
    return _parse(data, nights, params.get("cityName", city))


def price(hotel_id: str, rate_key: str, checkin: date, checkout: date, rooms: int, guests: int) -> dict | None:
    """Re-price a specific offer at checkout time; None if gone."""
    hid = hotel_id.replace("lite:", "")
    occupancies = [{"adults": guests, "children": [], "childrenAges": []} for _ in range(rooms)]
    data = _fetch_hotels("rates", hotelId=hid, checkin=checkin.isoformat(),
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
