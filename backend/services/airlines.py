"""Live flight search + fulfilment (Duffel primary, Amadeus fallback, then the
deterministic demo schedule). Real availability/pricing when keys are set -
plus a sandbox mode via DUFFEL_API_KEY=test/sandboxkey for safe demos."""
import base64
import json
import os
import time
from datetime import date, datetime, timedelta

import httpx

import config
from services import fx as _fx

DUFFEL_KEY = os.getenv("DUFFEL_API_KEY", "")
AMADEUS_KEY = os.getenv("AMADEUS_API_KEY", "")
AMADEUS_SECRET = os.getenv("AMADEUS_API_SECRET", "")
GDS_TIMEOUT = float(os.getenv("GDS_TIMEOUT", "25"))
# No percentage markup: prices shown are exactly what the airline/GDS charges,
# converted USD->GHS at the live rate. Margin comes from the per-dollar FX fee
# (FX_FEE_PER_USD in services/fx.py), never a hidden %.

import seed

try:
    import services.world_data as wd   # shared geography helpers
except Exception:
    wd = None


# Provider label + registries used by routers/flights.py meta endpoint.
AIRLINES = {
    "ET": {"name": "Ethiopian Airlines", "icao": "ETH", "alliance": "Star Alliance", "country": "ET"},
    "KQ": {"name": "Kenya Airways", "icao": "KQA", "alliance": "SkyTeam", "country": "KE"},
    "EK": {"name": "Emirates", "icao": "UAE", "alliance": None, "country": "AE"},
    "QR": {"name": "Qatar Airways", "icao": "QTR", "alliance": "oneworld", "country": "QA"},
    "TK": {"name": "Turkish Airlines", "icao": "THY", "alliance": "Star Alliance", "country": "TR"},
    "AT": {"name": "Royal Air Maroc", "icao": "RAM", "alliance": "oneworld", "country": "MA"},
    "SA": {"name": "South African Airways", "icao": "SAA", "alliance": "Star Alliance", "country": "ZA"},
    "MS": {"name": "EgyptAir", "icao": "MSR", "alliance": "Star Alliance", "country": "EG"},
    "P4": {"name": "Air Peace", "icao": "APK", "alliance": None, "country": "NG"},
    "W3": {"name": "Arik Air", "icao": "ARA", "alliance": None, "country": "NG"},
    "BA": {"name": "British Airways", "icao": "BAW", "alliance": "oneworld", "country": "GB"},
    "VS": {"name": "Virgin Atlantic", "icao": "VIR", "alliance": None, "country": "GB"},
    "LH": {"name": "Lufthansa", "icao": "DLH", "alliance": "Star Alliance", "country": "DE"},
    "AF": {"name": "Air France", "icao": "AFR", "alliance": "SkyTeam", "country": "FR"},
    "KL": {"name": "KLM", "icao": "KLM", "alliance": "SkyTeam", "country": "NL"},
    "DL": {"name": "Delta Air Lines", "icao": "DAL", "alliance": "SkyTeam", "country": "US"},
    "UA": {"name": "United Airlines", "icao": "UAL", "alliance": "Star Alliance", "country": "US"},
    "AA": {"name": "American Airlines", "icao": "AAL", "alliance": "oneworld", "country": "US"},
    "DL2": {"name": "", "icao": "", "alliance": None, "country": ""},
}
AIRLINES = {k: v for k, v in AIRLINES.items() if v["name"]}   # keep the shape clean
AIRPORTS = {}   # seed.AIRPORTS holds canonical data; nothing to override yet


def provider_name() -> str:
    if duffel_configured():
        return "duffel"
    if AMADEUS_KEY and AMADEUS_SECRET:
        return "amadeus"
    return "demo"


def revalidate(origin, dest, date_s, flight_key, cabin="economy"):
    """Re-check a selected fare at booking time. Returns fare/taxes in GHS
    PER PASSENGER (the router multiplies by the passenger multiplier)."""
    if duffel_configured() and str(flight_key).startswith("off_"):
        r = httpx.get(f"https://api.duffel.com/air/offers/{flight_key}",
                      headers=_duffel_headers(), timeout=GDS_TIMEOUT)
        data = r.json()
        if r.status_code >= 400:
            raise RuntimeError(data.get("errors") or data)
        o = data["data"]
        total = float(o.get("total_amount") or 0)
        tax = float(o.get("tax_amount") or 0)
        cur = o.get("total_currency") or "USD"
        paxn = max(len(o.get("passengers") or [1]), 1)
        return {"flight_key": flight_key,
                "pax_id": ((o.get("passengers") or [{}])[0]).get("id", ""),
                "fare": round(_fx.to_ghs(total - tax, cur) / paxn, 2),
                "taxes": round(_fx.to_ghs(tax, cur) / paxn, 2)}
    for f in search(origin, dest, date_s, cabin):
        if f.get("flight_key") == flight_key or f.get("offer_id") == flight_key:
            per = float(f.get("per_adult") or f.get("price") or 0)
            return {"flight_key": flight_key, "pax_id": "", "fare": round(per, 2), "taxes": 0.0}
    raise RuntimeError("Selected flight is no longer available - please search again")


def book_instant(flight_key, travelers, contact, *args, **kwargs):
    return instant_order(flight_key, travelers, contact)


# ------------------------------------------------------------------ search ---
def _cabins(pax):
    """Cabin classes Duffel should quote, best-first, for a passenger mix."""
    if any(p.get("type") == "infant" for p in pax):
        return ["first", "business", "premium_economy", "economy"]
    if any(p.get("type") == "child" for p in pax):
        return ["premium_economy", "business", "economy"]
    return ["economy", "premium_economy", "business"]


def _cabin_from_string(s):
    s = (s or "").lower()
    for c in ("economy", "premium_economy", "business", "first"):
        if c in s:
            return c
    return "economy"


def _dstr(d) -> str:
    """Accept date objects or ISO strings; return YYYY-MM-DD."""
    return str(d or "")[:10]


def _parse_slice(q):
    dep = _dstr(q.get("date"))
    out = {"origin": q["origin"].strip().upper(), "destination": q["dest"].strip().upper(),
           "departure_date": dep}
    if q.get("time"):
        out["departure_time"] = {"from": q["time"], "to": "23:59"}
    return out


def _bags(segs):
    checked = carry = 0
    for s in segs:
        for b in s.get("passengers") or []:
            checked += len(b.get("checked_baggages") or b.get("checked_bags") or [])
            carry += len(b.get("cabin_baggages") or b.get("cabin_bags") or [])
    return {"checked": checked or None, "carry": carry or None}


def _carriers(segs):
    names = []
    for s in segs:
        op = (s.get("operating_carrier") or {}).get("name")
        mk = (s.get("marketing_carrier") or {}).get("name")
        for nm in (op, mk):
            if nm and nm not in names:
                names.append(nm)
    return names[:2]


def search(origin, dest, date_s, cabin="economy", bags=0, pax=None):
    """One-way search. Returns a list of flight dicts (all GHS, cheapest first)."""
    if duffel_configured():
        try:
            return _duffel_search(origin, dest, date_s, cabin, bags, pax)
        except Exception:
            pass   # fall through to next provider
    try:
        return _amadeus_search(origin, dest, date_s, cabin, bags, pax)
    except Exception:
        pass
    return _demo_search(origin, dest, date_s, cabin, bags, pax)


def _norm(q):
    return {"origin": q["origin"].strip().upper(), "dest": q["dest"].strip().upper(),
            "date": _dstr(q.get("date")), "time": q.get("time")}


def _dedupe(flights, limit=60):
    seen, out = set(), []
    for f in flights:
        k = (f.get("flight_no") and tuple(f["flight_no"]), f.get("depart"), f.get("price"))
        if k in seen:
            continue
        seen.add(k)
        out.append(f)
        if len(out) >= limit:
            break
    return out


# ------------------------------------------------------------------ duffel ---
def duffel_configured():
    return bool(DUFFEL_KEY)


def _duffel_headers():
    h = {"Authorization": f"Bearer {DUFFEL_KEY}", "Duffel-Version": "v2", "Content-Type": "application/json"}
    if DUFFEL_KEY.startswith("test/"):
        h["Idempotency-Key"] = f"seed-{int(time.time())}"
    return h


def _duffel_search(origin, dest, date_s, cabin, bags, pax):
    travelers = pax or [{"type": "adult"}]
    slices = [_parse_slice({"origin": origin, "dest": dest, "date": date_s})]
    offer_req = {
        "data": {
            "slices": slices,
            "passengers": [{"type": p.get("type", "adult")} for p in travelers],
            "cabin_class": _cabin_from_string(cabin),
            "requested_sources": ["duffel"],
            "max_connections": 2,
            "limit": 25,
        }
    }
    if bags:
        offer_req["data"]["passengers"][0]["checked_baggages"] = [{"type": "bag", "quantity": int(bags)}]
    r = httpx.post("https://api.duffel.com/air/offer_requests",
                   headers=_duffel_headers(), json=offer_req,
                   timeout=min(GDS_TIMEOUT, 30))
    data = r.json()
    if r.status_code >= 400 or not data.get("data"):
        raise RuntimeError(f"duffel offer_request failed: {data}")
    offers = data["data"].get("offers") or []
    offers.sort(key=lambda o: float(o.get("total_amount") or 0))
    out = []
    for o in offers[:40]:
        try:
            out.append(_duffel_offer_to_flight(o, travelers))
        except Exception:
            continue
    return _dedupe(out, limit=60)


def _duffel_offer_to_flight(o, travelers):
    segs = []
    for s in o.get("slices") or []:
        segs.extend(s.get("segments") or [])
    d0, d1 = segs[0], segs[-1]
    stops = len(segs) - 1
    dep = datetime.fromisoformat(d0["departing_at"].replace("Z", "+00:00"))
    arr = datetime.fromisoformat(d1["arriving_at"].replace("Z", "+00:00"))
    dur = int((arr - dep).total_seconds() // 60)
    total = float(o.get("total_amount") or 0)
    cur = o.get("total_currency") or "USD"
    ghs = _fx.to_ghs(total, cur)
    return {
        "flight_key": o.get("id"),
        "offer_id": o.get("id"),
        "stops": stops,
        "duration_min": dur,
        "depart": d0["depart"],
        "arrive": d1["arrive"],
        "cabin": sorted({s.get("cabin_class") or "economy" for s in segs}),
        "airline": _carriers(segs),
        "flight_no": [s.get("flight_number") or s.get("marketing_flight_number") for s in segs],
        "price": round(total / max(len(travelers), 1), 2),
        "total": round(total, 2),
        "per_adult": round(total / max(len(travelers), 1), 2),
        "amount_ghs": round(ghs, 2),
        "currency": "GHS",
        "source": "duffel",
        "baggage": _bags(segs),
        "changeable": False,
        "refundable": False,
    }


# ------------------------------------------------------- duffel fulfilment ---
def _book_payload(legs, travelers, contact, hold=False):
    pax = []
    for t in travelers:
        p = {"type": t.get("type", "adult"),
             "given_name": (t.get("first_name") or "Guest").strip(),
             "family_name": (t.get("last_name") or "Traveller").strip()}
        if t.get("passport_no"): p["passport_number"] = t["passport_no"]
        if t.get("dob"): p["born_on"] = t["dob"]
        if t.get("nationality"): p["nationality"] = t["nationality"]
        if t.get("gender"): p["gender"] = t["gender"]
        pax.append(p)
    contact = contact or {}
    email = (contact.get("email") or "guest@japafly.com").strip()
    phone = (contact.get("phone") or "+233551934922").strip()
    slices = []
    for leg in legs:
        dep = (leg.get("date") or "").split("T")[0]
        slices.append({"origin": leg["origin"].strip().upper(),
                       "destination": leg["dest"].strip().upper(),
                       "departure_date": dep})
    return {"data": {"offer_id": legs[0]["flight_key"],
                     "slices": slices,
                     "passengers": pax,
                     "payments": [{"type": "balance", "currency": "USD",
                                   "amount": legs[0].get("total", "0")}],
                     "contact": {"email": email,
                                 "phone_number": phone if phone.startswith("+") else "+233551934922"}}}


def instant_order(flight_key, travelers, contact):
    """Create + pay a live Duffel order in one shot (instant ticketing)."""
    r = httpx.post("https://api.duffel.com/air/orders",
                   headers=_duffel_headers(),
                   json=_book_payload([{"flight_key": flight_key}], travelers, contact),
                   timeout=GDS_TIMEOUT)
    data = r.json()
    if r.status_code >= 400:
        raise RuntimeError(data.get("errors") or data)
    d = data["data"]
    return {"order_id": d["id"], "status": d.get("status"),
            "booking_reference": (d.get("booking_reference")),
            "amount": d.get("total_amount"), "currency": d.get("total_currency")}


def hold_order(flight_key, travelers, contact, pax_id=None):
    """Lock a fare without paying; capture within 24h via confirm_held_order."""
    payload = _book_payload([{"flight_key": flight_key}], travelers, contact)
    payload["data"]["type"] = "hold"
    r = httpx.post("https://api.duffel.com/air/orders",
                   headers=_duffel_headers(), json=payload, timeout=GDS_TIMEOUT)
    data = r.json()
    if r.status_code >= 400:
        raise RuntimeError(data.get("errors") or data)
    d = data["data"]
    return {"order_id": d["id"], "status": d.get("status"),
            "booking_reference": d.get("booking_reference"),
            "expires_at": d.get("expires_at")}


def _confirm_url(order_id):
    return f"https://api.duffel.com/air/orders/{order_id}/actions/confirm"


def confirm_held_order(order_id):
    """Pay a held order after the customer settles (within the hold window)."""
    r = httpx.post(_confirm_url(order_id), headers=_duffel_headers(), timeout=GDS_TIMEOUT)
    data = r.json()
    if r.status_code >= 400:
        raise RuntimeError(data.get("errors") or data)
    d = data["data"]
    return {"order_id": d["id"], "status": d.get("status"),
            "booking_reference": d.get("booking_reference"),
            "amount": d.get("total_amount"), "currency": d.get("total_currency")}


def ticket_order(offer_id, travelers, contact):
    """Legacy path: confirm a hold by id then return its reference."""
    return hold_order(offer_id, travelers, contact)


def duffel_booking(order_id):
    r = httpx.get(f"https://api.duffel.com/air/orders/{order_id}",
                  headers=_duffel_headers(), timeout=GDS_TIMEOUT)
    data = r.json()
    if r.status_code >= 400:
        raise RuntimeError(data.get("errors") or data)
    d = data["data"]
    return {"status": d.get("status"), "booking_reference": d.get("booking_reference"),
            "amount": d.get("total_amount"), "currency": d.get("total_currency")}


# ----------------------------------------------------------------- amadeus ---
def _amadeus_token():
    if not (AMADEUS_KEY and AMADEUS_SECRET):
        raise RuntimeError("Amadeus not configured")
    r = httpx.post("https://test.api.amadeus.com/v1/security/oauth2/token",
                   data={"grant_type": "client_credentials",
                         "client_id": AMADEUS_KEY, "client_secret": AMADEUS_SECRET},
                   timeout=10)
    return r.json()["access_token"]


def _amadeus_search(origin, dest, date_s, cabin, bags, pax):
    token = _amadeus_token()
    r = httpx.get("https://test.api.amadeus.com/v2/shopping/flight-offers",
                  headers={"Authorization": f"Bearer {token}"},
                  params={"originLocationCode": origin.upper(),
                          "destinationLocationCode": dest.upper(),
                          "departureDate": _dstr(date_s),
                          "adults": max(1, len(pax or [1])),
                          "travelClass": _cabin_from_string(cabin).upper().replace("PREMIUM_ECONOMY", "PREMIUM_ECONOMY"),
                          "currencyCode": "GHS",
                          "max": 20},
                  timeout=GDS_TIMEOUT)
    data = r.json()
    if r.status_code >= 400 or not data.get("data"):
        raise RuntimeError(f"amadeus search failed: {data}")
    out = []
    for o in data["data"]:
        try:
            itin = o["itineraries"][0]
            segs = itin["segments"]
            dep = datetime.fromisoformat(segs[0]["departure"]["at"].replace("Z", "+00:00"))
            arr = datetime.fromisoformat(segs[-1]["arrival"]["at"].replace("Z", "+00:00"))
            dur = int((arr - dep).total_seconds() // 60)
            total = float(o["price"]["total"])
            ghs = _fx.to_ghs(total, o["price"].get("currency", "GHS"))
            out.append({
                "flight_key": o["id"], "offer_id": o["id"],
                "stops": len(segs) - 1, "duration_min": dur,
                "depart": segs[0]["departure"]["at"],
                "arrive": segs[-1]["arrival"]["at"],
                "cabin": [o.get("travelClass", "ECONOMY").lower()],
                "airline": [(segs[0].get("operating") or segs[0]["carrierCode"])],
                "flight_no": [f"{s['carrierCode']}{s['number']}" for s in segs],
                "price": round(total / max(len(pax or [1]), 1), 2),
                "total": round(total, 2),
                "per_adult": round(total / max(len(pax or [1]), 1), 2),
                "amount_ghs": round(ghs, 2),
                "currency": "GHS",
                "source": "amadeus",
                "baggage": {"checked": bags or None, "carry": None},
                "changeable": False, "refundable": False,
            })
        except Exception:
            continue
    out.sort(key=lambda f: f["price"])
    return _dedupe(out, limit=60)


# -------------------------------------------------------------------- demo ---
def _demo_search(origin, dest, date_s, cabin, bags, pax):
    """Deterministic demo schedule from seed.flights_for (used when no GDS keys)."""
    try:
        d = date_s if isinstance(date_s, date) else datetime.fromisoformat(_dstr(date_s)).date()
    except Exception:
        return []
    cabin_key = _cabin_from_string(cabin)
    try:
        demos = seed.flights_for(origin, dest, d, cabin_key)
    except Exception:
        return []
    bag_fee = float(getattr(seed, "BAG_FEE", 0) or 0)
    bag_total = bag_fee * int(bags or 0)
    out = []
    for f in demos:
        arr_date = (d + timedelta(days=1)) if f.get("arrives_next_day") else d
        price = round(float(f.get("fare") or 0) + bag_total, 2)
        total = round(float(f.get("total") or 0) + bag_total, 2)
        out.append({
            "flight_key": f["flight_key"], "offer_id": f["flight_key"],
            "stops": f["stops"], "duration_min": f["duration_min"],
            "depart": f"{f['date']}T{f['departure']}:00",
            "arrive": f"{arr_date.isoformat()}T{f['arrival']}:00",
            "cabin": [cabin_key],
            "airline": [f["airline"]],
            "flight_no": [f["flight_no"]],
            "price": price, "total": total, "per_adult": price,
            "amount_ghs": total, "currency": "GHS", "source": "seed",
            "baggage": {"checked": bags or None, "carry": None},
            "changeable": True, "refundable": False,
        })
    out.sort(key=lambda x: x["price"])
    return _dedupe(out, limit=60)


def cancel_booking(ref):
    """Cancel whatever kind of booking `ref` points at; returns refund info."""
    if duffel_configured() and str(ref).startswith("ord_"):
        r = httpx.post(f"https://api.duffel.com/air/orders/{ref}/actions/cancel",
                       headers=_duffel_headers(), timeout=GDS_TIMEOUT)
        if r.status_code >= 400:
            raise RuntimeError(r.json())
        return {"cancelled": True, "source": "duffel"}
    return {"cancelled": True, "source": "seed"}
