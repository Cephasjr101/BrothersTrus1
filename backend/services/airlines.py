# World-standard airline data + pluggable flight-data providers (IATA/ICAO).
#
# Providers:
#   DemoProvider    — deterministic offline schedule (default, zero config)
#   AmadeusProvider — real live fares via Amadeus for Developers (the airline
#                     industry's standard GDS API). Activates automatically when
#                     AMADEUS_API_KEY + AMADEUS_SECRET are set in .env.
#
# Both return the same flight-offer shape, so the rest of the app is unchanged.
import hashlib
import json
import os
import urllib.parse
import urllib.request
from datetime import date, datetime

import re

import seed

# ------------------------------------------------------------------ airlines (IATA -> ICAO, alliance)
AIRLINES = {
    "P4": {"name": "Air Peace",          "icao": "APK", "country": "Nigeria",        "alliance": None},
    "W3": {"name": "Arik Air",           "icao": "ARA", "country": "Nigeria",        "alliance": None},
    "9J": {"name": "Dana Air",           "icao": "DAN", "country": "Nigeria",        "alliance": None},
    "QI": {"name": "Ibom Air",           "icao": "IBM", "country": "Nigeria",        "alliance": None},
    "U5": {"name": "United Nigeria",     "icao": "UNA", "country": "Nigeria",        "alliance": None},
    "EK": {"name": "Emirates",           "icao": "UAE", "country": "UAE",            "alliance": None},
    "BA": {"name": "British Airways",    "icao": "BAW", "country": "United Kingdom", "alliance": "oneworld"},
    "QR": {"name": "Qatar Airways",      "icao": "QTR", "country": "Qatar",          "alliance": "oneworld"},
    "TK": {"name": "Turkish Airlines",   "icao": "THY", "country": "Türkiye",        "alliance": "Star Alliance"},
    "ET": {"name": "Ethiopian Airlines", "icao": "ETH", "country": "Ethiopia",       "alliance": "Star Alliance"},
    "AF": {"name": "Air France",         "icao": "AFR", "country": "France",         "alliance": "SkyTeam"},
    "MS": {"name": "EgyptAir",           "icao": "MSR", "country": "Egypt",          "alliance": "Star Alliance"},
    "KQ": {"name": "Kenya Airways",      "icao": "KQA", "country": "Kenya",          "alliance": "SkyTeam"},
    "AT": {"name": "Royal Air Maroc",    "icao": "RAM", "country": "Morocco",        "alliance": "oneworld"},
    "DL": {"name": "Delta Air Lines",    "icao": "DAL", "country": "United States",  "alliance": "SkyTeam"},
    "VS": {"name": "Virgin Atlantic",    "icao": "VIR", "country": "United Kingdom", "alliance": "SkyTeam"},
}

# ------------------------------------------------------------------ airports (IATA -> ICAO, tz, geo)
AIRPORTS = {
    "LOS": {"icao": "DNMM", "city": "Lagos",         "country": "Nigeria",        "tz": "Africa/Lagos",   "lat": 6.577,  "lon": 3.321},
    "ABV": {"icao": "DNAA", "city": "Abuja",         "country": "Nigeria",        "tz": "Africa/Lagos",   "lat": 9.007,  "lon": 7.263},
    "PHC": {"icao": "DNPO", "city": "Port Harcourt", "country": "Nigeria",        "tz": "Africa/Lagos",   "lat": 5.015,  "lon": 6.950},
    "ACC": {"icao": "DGAA", "city": "Accra",         "country": "Ghana",          "tz": "Africa/Accra",   "lat": 5.605,  "lon": -0.167},
    "LHR": {"icao": "EGLL", "city": "London",        "country": "United Kingdom", "tz": "Europe/London",  "lat": 51.470, "lon": -0.454},
    "DXB": {"icao": "OMDB", "city": "Dubai",         "country": "UAE",            "tz": "Asia/Dubai",     "lat": 25.253, "lon": 55.365},
    "JFK": {"icao": "KJFK", "city": "New York",      "country": "United States",  "tz": "America/New_York","lat": 40.641, "lon": -73.778},
    "JNB": {"icao": "FAOR", "city": "Johannesburg",  "country": "South Africa",   "tz": "Africa/Johannesburg", "lat": -26.136, "lon": 28.241},
    "CDG": {"icao": "LFPG", "city": "Paris",         "country": "France",         "tz": "Europe/Paris",   "lat": 49.010, "lon": 2.548},
    "IST": {"icao": "LTFM", "city": "Istanbul",      "country": "Türkiye",        "tz": "Europe/Istanbul","lat": 41.275, "lon": 28.752},
    "NBO": {"icao": "HKJK", "city": "Nairobi",       "country": "Kenya",          "tz": "Africa/Nairobi", "lat": -1.319, "lon": 36.928},
    "CAI": {"icao": "HECA", "city": "Cairo",         "country": "Egypt",          "tz": "Africa/Cairo",   "lat": 30.122, "lon": 31.406},
}

TRAVEL_CLASS = {"economy": "ECONOMY", "premium": "PREMIUM_ECONOMY",
                "business": "BUSINESS", "first": "FIRST"}


# ================================================================== Demo provider (offline)
def _demo_search(origin: str, dest: str, d: date, cabin: str) -> list[dict]:
    return seed.flights_for(origin, dest, d, cabin)


def _demo_revalidate(origin: str, dest: str, d: date, flight_key: str, cabin: str):
    return seed.find_flight(origin, dest, d, flight_key, cabin)


# ================================================================== Amadeus provider (live GDS)
class AmadeusError(RuntimeError):
    pass


_amadeus_token = {"value": None, "expires": 0}


def amadeus_configured() -> bool:
    return bool(os.getenv("AMADEUS_API_KEY") and os.getenv("AMADEUS_SECRET"))


def _amadeus_base() -> str:
    return "https://api.amadeus.com" if os.getenv("AMADEUS_PRODUCTION") == "1" else "https://test.api.amadeus.com"


def _amadeus_token() -> str:
    import time
    if _amadeus_token["value"] and time.time() < _amadeus_token["expires"] - 60:
        return _amadeus_token["value"]
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": os.getenv("AMADEUS_API_KEY"),
        "client_secret": os.getenv("AMADEUS_SECRET")}).encode()
    req = urllib.request.Request(_amadeus_base() + "/v1/security/oauth2/token",
                                 data=body, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.loads(r.read().decode())
    except Exception as exc:
        raise AmadeusError(f"Amadeus authentication failed: {exc}")
    _amadeus_token.update(value=data["access_token"], expires=time.time() + data.get("expires_in", 900))
    return _amadeus_token["value"]


def _amadeus_get(path: str, params: dict) -> dict:
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{_amadeus_base()}{path}?{qs}",
                                 headers={"Authorization": f"Bearer {_amadeus_token()}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read().decode()).get("errors", [{}])[0].get("detail", "")
        except Exception:
            pass
        raise AmadeusError(f"Amadeus flight search failed ({exc.code}): {detail or exc.reason}")


def _offer_slice_to_flight(offer: dict, slice_i: int, origin: str, dest: str,
                           d: date, cabin: str) -> dict | None:
    slices = offer.get("itineraries", [])
    if slice_i >= len(slices):
        return None
    itin = slices[slice_i]
    segs = itin.get("segments", [])
    if not segs:
        return None
    first, last = segs[0], segs[-1]
    carrier, number = first["carrierCode"], first["number"]
    dep_t = datetime.fromisoformat(first["departure"]["at"])
    arr_t = datetime.fromisoformat(last["arrival"]["at"])
    price = offer.get("price", {})
    total = float(price.get("grandTotal", 0))
    base = float(price.get("base", total))
    airline = AIRLINES.get(carrier, {"name": carrier, "icao": carrier, "country": "", "alliance": None})
    colors = ["#1F2D54", "#2E9BD6", "#1E7A3C", "#26407A", "#17679E", "#166030"]
    color = seed.AIRLINES.get(carrier, {}).get("color") or colors[int(hashlib.sha1(carrier.encode()).hexdigest()[:2], 16) % len(colors)]
    dm = _re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?$", itin.get("duration", ""))
    duration_min = (int(dm.group(1) or 0) * 60 + int(dm.group(2) or 0)) if dm else 0
    key_src = f"{carrier}{number}:{origin}-{dest}:{d.isoformat()}"
    return {
        "flight_key": hashlib.sha1(key_src.encode()).hexdigest()[:12],
        "airline_code": carrier,
        "airline": airline["name"],
        "airline_color": color,
        "flight_no": f"{carrier}{number}",
        "aircraft": (first.get("aircraft", {}) or {}).get("code", ""),
        "origin": first["departure"]["iataCode"],
        "dest": last["arrival"]["iataCode"],
        "date": d.isoformat(),
        "departure": dep_t.strftime("%H:%M"),
        "arrival": arr_t.strftime("%H:%M"),
        "arrives_next_day": arr_t.date() > dep_t.date(),
        "duration_min": duration_min,
        "stops": max(len(segs) - 1, 0),
        "cabin": seed.CABINS[cabin]["label"],
        "fare": round(base),
        "taxes": round(total - base),
        "total": round(total),
        "refundable": bool(offer.get("pricingOptions", {}).get("refundableFare", False)),
        "live": True,
    }


def _amadeus_search(origin: str, dest: str, d: date, cabin: str, adults: int = 1) -> list[dict]:
    data = _amadeus_get("/v2/shopping/flight-offers", {
        "originLocationCode": origin,
        "destinationLocationCode": dest,
        "departureDate": d.isoformat(),
        "adults": adults,
        "currencyCode": "GHS",
        "travelClass": TRAVEL_CLASS.get(cabin, "ECONOMY"),
        "max": 20,
    })
    out = []
    for offer in data.get("data", []):
        f = _offer_slice_to_flight(offer, 0, origin, dest, d, cabin)
        if f:
            out.append(f)
    return sorted(out, key=lambda x: x["total"])


def _amadeus_revalidate(origin: str, dest: str, d: date, flight_key: str, cabin: str):
    """World-standard practice: re-price at booking time from a fresh search."""
    for f in _amadeus_search(origin, dest, d, cabin):
        if f["flight_key"] == flight_key:
            return f
    return None


# ================================================================== dispatch
def provider_name() -> str:
    return "amadeus" if amadeus_configured() else "demo"


def search(origin: str, dest: str, d: date, cabin: str = "economy") -> list[dict]:
    if amadeus_configured():
        return _amadeus_search(origin, dest, d, cabin)
    return _demo_search(origin, dest, d, cabin)


def revalidate(origin: str, dest: str, d: date, flight_key: str, cabin: str = "economy"):
    if amadeus_configured():
        return _amadeus_revalidate(origin, dest, d, flight_key, cabin)
    return _demo_revalidate(origin, dest, d, flight_key, cabin)
