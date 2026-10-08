"""Catalog data + the pricing/availability engine for Brother'sTrust Travel.

The flight schedule is generated deterministically from route + date, so a
search result can be re-validated and re-priced server-side at booking time
without storing a flight database. Hotels, cars and visa fees are static
catalogs; availability is computed live from the bookings / visa_slots tables.
"""
import hashlib
from datetime import date, datetime, timedelta

CURRENCY = "GHS"            # Ghanaian cedi
TAXES = 250                 # per-ticket airport taxes & surcharges (GH\u00A2)
SERVICE_FEE = 100           # flat service charge per booking (GH\u00A2)
VAT = 0.15                  # 15% Ghana VAT on hotel & car subtotals


def ghs(ngn: float) -> int:
    """Re-denominate legacy catalog values to cedis (~100:1 placeholder rate)."""
    return max(1, round(ngn / 100))

# ----------------------------------------------------------------- airports
AIRPORTS = {
    "LOS": {"city": "Lagos",       "name": "Murtala Muhammel Intl",        "country": "Nigeria"},
    "ABV": {"city": "Abuja",       "name": "Nnamdi Azikiwe Intl",          "country": "Nigeria"},
    "PHC": {"city": "Port Harcourt","name": "Port Harcourt Intl",          "country": "Nigeria"},
    "ACC": {"city": "Accra",       "name": "Kotoka Intl",                  "country": "Ghana"},
    "LHR": {"city": "London",      "name": "Heathrow",                     "country": "United Kingdom"},
    "DXB": {"city": "Dubai",       "name": "Dubai Intl",                   "country": "United Arab Emirates"},
    "JFK": {"city": "New York",    "name": "John F. Kennedy Intl",         "country": "United States"},
    "JNB": {"city": "Johannesburg","name": "O.R. Tambo Intl",              "country": "South Africa"},
    "CDG": {"city": "Paris",       "name": "Charles de Gaulle",            "country": "France"},
    "IST": {"city": "Istanbul",    "name": "Istanbul Airport",             "country": "Türkiye"},
    "NBO": {"city": "Nairobi",     "name": "Jomo Kenyatta Intl",           "country": "Kenya"},
    "CAI": {"city": "Cairo",       "name": "Cairo Intl",                   "country": "Egypt"},
}

AIRLINES = {
    "P4": {"name": "Air Peace",        "color": "#0a7a3d"},
    "W3": {"name": "Arik Air",         "color": "#d0342c"},
    "9J": {"name": "Dana Air",         "color": "#f26722"},
    "QI": {"name": "Ibom Air",         "color": "#1f6fb4"},
    "U5": {"name": "United Nigeria",   "color": "#6b3fa0"},
    "EK": {"name": "Emirates",         "color": "#c8102e"},
    "BA": {"name": "British Airways",  "color": "#075aaa"},
    "QR": {"name": "Qatar Airways",    "color": "#5c0632"},
    "TK": {"name": "Turkish Airlines", "color": "#e81932"},
    "ET": {"name": "Ethiopian Airlines","color": "#1c7a1c"},
    "AF": {"name": "Air France",       "color": "#002157"},
    "MS": {"name": "EgyptAir",         "color": "#0b6bac"},
    "KQ": {"name": "Kenya Airways",    "color": "#b02a30"},
    "AT": {"name": "Royal Air Maroc",  "color": "#c1272d"},
}

# base = economy one-way fare (GH\u00A2), duration in minutes
ROUTES = {
    "LOS-ABV": {"base": 55_000,  "duration": 65,  "stops": 0, "airlines": ["P4", "W3", "9J", "QI", "U5"]},
    "LOS-PHC": {"base": 45_000,  "duration": 60,  "stops": 0, "airlines": ["P4", "W3", "9J", "U5"]},
    "ABV-PHC": {"base": 40_000,  "duration": 55,  "stops": 0, "airlines": ["P4", "W3", "QI"]},
    "LOS-ACC": {"base": 120_000, "duration": 75,  "stops": 0, "airlines": ["P4", "KQ", "AT"]},
    "LOS-DXB": {"base": 650_000, "duration": 470, "stops": 0, "airlines": ["EK", "QR", "TK"]},
    "ABV-DXB": {"base": 680_000, "duration": 500, "stops": 0, "airlines": ["QR", "TK", "ET"]},
    "LOS-LHR": {"base": 850_000, "duration": 405, "stops": 0, "airlines": ["BA", "VS", "QR"]},
    "ABV-LHR": {"base": 900_000, "duration": 420, "stops": 0, "airlines": ["BA", "QR"]},
    "LOS-JFK": {"base": 1_250_000,"duration": 660,"stops": 0, "airlines": ["DL", "QR", "ET"]},
    "LOS-JNB": {"base": 520_000, "duration": 360, "stops": 0, "airlines": ["ET", "KQ", "AT"]},
    "LOS-CDG": {"base": 780_000, "duration": 420, "stops": 0, "airlines": ["AF", "BA", "TK"]},
    "LOS-IST": {"base": 700_000, "duration": 450, "stops": 0, "airlines": ["TK", "QR"]},
    "LOS-NBO": {"base": 480_000, "duration": 330, "stops": 0, "airlines": ["KQ", "ET"]},
    "LOS-CAI": {"base": 600_000, "duration": 340, "stops": 0, "airlines": ["MS", "ET"]},
}
# extra carriers referenced above
AIRLINES.update({
    "VS": {"name": "Virgin Atlantic",  "color": "#b31942"},
    "DL": {"name": "Delta Air Lines",  "color": "#003366"},
})

CABINS = {
    "economy":  {"label": "Economy",  "mult": 1.0},
    "premium":  {"label": "Premium",  "mult": 1.35},
    "business": {"label": "Business", "mult": 2.45},
    "first":    {"label": "First",    "mult": 3.9},
}
AIRCRAFT = ["Boeing 737-800", "Airbus A320", "Boeing 777-300ER", "Airbus A350-900", "Embraer E195"]

# ----------------------------------------------------------------- flights
def _route(origin: str, dest: str) -> dict | None:
    return ROUTES.get(f"{origin}-{dest}") or ROUTES.get(f"{dest}-{origin}")


def _day_factor(d: date) -> float:
    return {4: 1.15, 5: 1.08, 6: 1.15}.get(d.weekday(), 1.0)   # Fri/Sat/Sun demand


def _advance_factor(d: date) -> float:
    days = (d - date.today()).days
    if days >= 21: return 0.85
    if days >= 14: return 0.90
    if days >= 7:  return 0.95
    if days >= 2:  return 1.00
    return 1.15


def flights_for(origin: str, dest: str, d: date, cabin: str = "economy") -> list[dict]:
    route = _route(origin, dest)
    if not route or origin == dest:
        return []
    iso = d.isoformat()
    seed = int(hashlib.sha1(f"{origin}{dest}{iso}".encode()).hexdigest()[:4], 16)
    count = 4 + seed % 4                                   # 4-7 flights per day
    departures = ["06:40", "08:15", "10:30", "13:05", "15:45", "18:20", "20:55"][:count]
    out = []
    for i, dep in enumerate(departures):
        airline = route["airlines"][int(hashlib.sha1(f"{iso}{i}{origin}{dest}".encode()).hexdigest()[:4], 16)
                                    % len(route["airlines"])]
        dh, dm = map(int, dep.split(":"))
        dur = route["duration"] + (35 if route["stops"] else 0)
        arr_dt = datetime.combine(d, datetime.min.time()) + timedelta(hours=dh, minutes=dm + dur)
        fare = round(ghs(route["base"]) * CABINS[cabin]["mult"] * _day_factor(d) * _advance_factor(d))
        key = hashlib.sha1(f"{origin}-{dest}:{iso}:{i}".encode()).hexdigest()[:12]
        out.append({
            "flight_key": key,
            "airline_code": airline,
            "airline": AIRLINES[airline]["name"],
            "airline_color": AIRLINES[airline]["color"],
            "flight_no": f"{airline}{100 + (seed + i * 37) % 800}",
            "aircraft": AIRCRAFT[(seed + i) % len(AIRCRAFT)],
            "origin": origin, "dest": dest, "date": iso,
            "departure": dep, "arrival": arr_dt.strftime("%H:%M"),
            "arrives_next_day": arr_dt.date() > d,
            "duration_min": dur,
            "stops": route["stops"],
            "cabin": CABINS[cabin]["label"],
            "fare": fare, "taxes": TAXES, "total": fare + TAXES,
            "refundable": True,
        })
    return out


def find_flight(origin: str, dest: str, d: date, flight_key: str, cabin: str) -> dict | None:
    for f in flights_for(origin, dest, d, cabin):
        if f["flight_key"] == flight_key:
            return f
    return None


def pax_multiplier(passengers: list[dict]) -> float:
    mult = 0.0
    for p in passengers:
        t = (p.get("type") or "adult").lower()
        mult += {"adult": 1.0, "child": 0.75, "infant": 0.1}.get(t, 1.0)
    return mult


# ----------------------------------------------------------------- hotels
HOTELS = [
    # Lagos
    {"id": "h-lag-1", "name": "Eko Hotels & Suites", "city": "Lagos", "country": "Nigeria", "stars": 5, "rating": 4.5, "reviews": 3120, "area": "Victoria Island", "cover": "lagos-palm",
     "rooms": [{"type": "Deluxe King", "price": 180_000, "size": "38m²", "occupancy": 2, "count": 20, "perks": ["Sea view", "Breakfast", "Free Wi-Fi"]},
               {"type": "Executive Suite", "price": 320_000, "size": "58m²", "occupancy": 3, "count": 8, "perks": ["Lounge access", "Breakfast", "Sea view"]}]},
    {"id": "h-lag-2", "name": "The Federal Palace Hotel", "city": "Lagos", "country": "Nigeria", "stars": 5, "rating": 4.3, "reviews": 1875, "area": "Ahmadu Bello Way, VI", "cover": "lagos-palm",
     "rooms": [{"type": "Classic Room", "price": 145_000, "size": "32m²", "occupancy": 2, "count": 24, "perks": ["Pool", "Breakfast"]},
               {"type": "Superior Room", "price": 195_000, "size": "40m²", "occupancy": 2, "count": 12, "perks": ["Pool", "Breakfast", "Ocean view"]}]},
    {"id": "h-lag-3", "name": "Lagos Continental Hotel", "city": "Lagos", "country": "Nigeria", "stars": 5, "rating": 4.4, "reviews": 2210, "area": "Kofo Abayomi, VI", "cover": "lagos-sky",
     "rooms": [{"type": "Premier Room", "price": 165_000, "size": "36m²", "occupancy": 2, "count": 30, "perks": ["Sky bar", "Breakfast", "Gym"]},
               {"type": "Continental Suite", "price": 350_000, "size": "64m²", "occupancy": 3, "count": 6, "perks": ["Butler service", "Sky bar"]}]},
    {"id": "h-lag-4", "name": "Radisson Blu Anchorage", "city": "Lagos", "country": "Nigeria", "stars": 5, "rating": 4.6, "reviews": 1540, "area": "Victoria Island waterfront", "cover": "lagos-water",
     "rooms": [{"type": "Standard Room", "price": 175_000, "size": "30m²", "occupancy": 2, "count": 26, "perks": ["Waterfront", "Breakfast"]},
               {"type": "Business Class", "price": 240_000, "size": "42m²", "occupancy": 2, "count": 10, "perks": ["Waterfront", "Lounge access"]}]},
    {"id": "h-lag-5", "name": "Protea Hotel Ikeja", "city": "Lagos", "country": "Nigeria", "stars": 4, "rating": 4.1, "reviews": 980, "area": "Ikeja GRA", "cover": "lagos-sky",
     "rooms": [{"type": "Standard King", "price": 85_000, "size": "28m²", "occupancy": 2, "count": 40, "perks": ["Free Wi-Fi", "Gym"]},
               {"type": "Junior Suite", "price": 140_000, "size": "45m²", "occupancy": 3, "count": 8, "perks": ["Lounge access", "Breakfast"]}]},
    {"id": "h-lag-6", "name": "ibis Lagos Airport", "city": "Lagos", "country": "Nigeria", "stars": 3, "rating": 3.8, "reviews": 760, "area": "Murtala Muhammed Airport", "cover": "lagos-sky",
     "rooms": [{"type": "Standard Twin", "price": 60_000, "size": "22m²", "occupancy": 2, "count": 50, "perks": ["Airport shuttle", "Free Wi-Fi"]}]},
    # Abuja
    {"id": "h-abv-1", "name": "Transcorp Hilton Abuja", "city": "Abuja", "country": "Nigeria", "stars": 5, "rating": 4.5, "reviews": 2740, "area": "Maitama", "cover": "abuja-rock",
     "rooms": [{"type": "Hilton King", "price": 210_000, "size": "40m²", "occupancy": 2, "count": 40, "perks": ["Pool", "Breakfast", "Tennis"]},
               {"type": "Executive Suite", "price": 390_000, "size": "70m²", "occupancy": 3, "count": 10, "perks": ["Lounge access", "Breakfast"]}]},
    {"id": "h-abv-2", "name": "Sheraton Abuja Hotel", "city": "Abuja", "country": "Nigeria", "stars": 5, "rating": 4.3, "reviews": 1980, "area": "Ladi Kwali Way, Wuse", "cover": "abuja-rock",
     "rooms": [{"type": "Deluxe Room", "price": 155_000, "size": "34m²", "occupancy": 2, "count": 30, "perks": ["Pool", "Gym"]},
               {"type": "Club Room", "price": 220_000, "size": "44m²", "occupancy": 2, "count": 12, "perks": ["Club lounge", "Breakfast"]}]},
    {"id": "h-abv-3", "name": "Fraser Suites Abuja", "city": "Abuja", "country": "Nigeria", "stars": 4, "rating": 4.2, "reviews": 870, "area": "Central Business District", "cover": "abuja-city",
     "rooms": [{"type": "Studio", "price": 120_000, "size": "35m²", "occupancy": 2, "count": 25, "perks": ["Kitchenette", "Breakfast"]},
               {"type": "One Bedroom", "price": 175_000, "size": "52m²", "occupancy": 3, "count": 10, "perks": ["Kitchenette", "Lounge access"]}]},
    {"id": "h-abv-4", "name": "Nicon Luxury Hotel", "city": "Abuja", "country": "Nigeria", "stars": 4, "rating": 4.0, "reviews": 650, "area": "Maitama", "cover": "abuja-city",
     "rooms": [{"type": "Superior King", "price": 95_000, "size": "30m²", "occupancy": 2, "count": 35, "perks": ["Pool", "Free Wi-Fi"]}]},
    # Accra
    {"id": "h-acc-1", "name": "Kempinski Hotel Gold Coast City", "city": "Accra", "country": "Ghana", "stars": 5, "rating": 4.6, "reviews": 1320, "area": "Gamel Abdul Nasser Ave", "cover": "accra-coast",
     "rooms": [{"type": "Deluxe King", "price": 240_000, "size": "42m²", "occupancy": 2, "count": 30, "perks": ["Pool", "Spa", "Breakfast"]},
               {"type": "Kempinski Suite", "price": 450_000, "size": "75m²", "occupancy": 3, "count": 8, "perks": ["Butler service", "Spa access"]}]},
    {"id": "h-acc-2", "name": "Mövenpick Ambassador Hotel", "city": "Accra", "country": "Ghana", "stars": 5, "rating": 4.4, "reviews": 1690, "area": "Independence Ave", "cover": "accra-coast",
     "rooms": [{"type": "Superior Room", "price": 190_000, "size": "36m²", "occupancy": 2, "count": 35, "perks": ["Pool", "Breakfast"]},
               {"type": "Junior Suite", "price": 300_000, "size": "55m²", "occupancy": 3, "count": 10, "perks": ["Lounge access", "Breakfast"]}]},
    {"id": "h-acc-3", "name": "Labadi Beach Hotel", "city": "Accra", "country": "Ghana", "stars": 4, "rating": 4.1, "reviews": 1105, "area": "Labadi Beach", "cover": "accra-coast",
     "rooms": [{"type": "Ocean View", "price": 150_000, "size": "32m²", "occupancy": 2, "count": 40, "perks": ["Private beach", "Breakfast"]}]},
    {"id": "h-acc-4", "name": "Golden Tulip Accra", "city": "Accra", "country": "Ghana", "stars": 4, "rating": 3.9, "reviews": 820, "area": "Liberation Road", "cover": "accra-city",
     "rooms": [{"type": "Standard Room", "price": 95_000, "size": "26m²", "occupancy": 2, "count": 45, "perks": ["Pool", "Free Wi-Fi"]}]},
    # Dubai
    {"id": "h-dxb-1", "name": "Address Downtown", "city": "Dubai", "country": "UAE", "stars": 5, "rating": 4.8, "reviews": 4210, "area": "Downtown Dubai", "cover": "dubai-towers",
     "rooms": [{"type": "Deluxe Fountain View", "price": 420_000, "size": "48m²", "occupancy": 2, "count": 40, "perks": ["Burj view", "Pool", "Breakfast"]},
               {"type": "Signature Suite", "price": 780_000, "size": "85m²", "occupancy": 3, "count": 8, "perks": ["Lounge access", "Burj view"]}]},
    {"id": "h-dxb-2", "name": "Atlantis, The Palm", "city": "Dubai", "country": "UAE", "stars": 5, "rating": 4.7, "reviews": 5630, "area": "Palm Jumeirah", "cover": "dubai-palm",
     "rooms": [{"type": "Ocean King", "price": 520_000, "size": "45m²", "occupancy": 2, "count": 60, "perks": ["Aquaventure access", "Breakfast"]},
               {"type": "Underwater Suite", "price": 1_850_000, "size": "165m²", "occupancy": 3, "count": 2, "perks": ["Aquarium view", "Butler service"]}]},
    {"id": "h-dxb-3", "name": "Rove Downtown", "city": "Dubai", "country": "UAE", "stars": 3, "rating": 4.3, "reviews": 3410, "area": "Downtown Dubai", "cover": "dubai-towers",
     "rooms": [{"type": "Rove Room", "price": 165_000, "size": "24m²", "occupancy": 2, "count": 80, "perks": ["Free Wi-Fi", "Gym"]}]},
    {"id": "h-dxb-4", "name": "Hilton Garden Inn Dubai Mall", "city": "Dubai", "country": "UAE", "stars": 4, "rating": 4.2, "reviews": 2150, "area": "Sheikh Zayed Road", "cover": "dubai-towers",
     "rooms": [{"type": "King Room", "price": 210_000, "size": "30m²", "occupancy": 2, "count": 50, "perks": ["Breakfast", "Pool"]}]},
    # London / New York / Paris / Nairobi
    {"id": "h-lon-1", "name": "The Savoy", "city": "London", "country": "United Kingdom", "stars": 5, "rating": 4.8, "reviews": 2890, "area": "Strand", "cover": "london-river",
     "rooms": [{"type": "Superior Queen", "price": 610_000, "size": "35m²", "occupancy": 2, "count": 25, "perks": ["River view", "Breakfast", "Spa"]}]},
    {"id": "h-lon-2", "name": "Park Plaza Westminster Bridge", "city": "London", "country": "United Kingdom", "stars": 4, "rating": 4.2, "reviews": 3560, "area": "Southbank", "cover": "london-river",
     "rooms": [{"type": "Standard Double", "price": 310_000, "size": "22m²", "occupancy": 2, "count": 60, "perks": ["Breakfast", "Pool"]}]},
    {"id": "h-nyc-1", "name": "Hilton New York Times Square", "city": "New York", "country": "United States", "stars": 4, "rating": 4.1, "reviews": 4320, "area": "Times Square, Manhattan", "cover": "nyc-sky",
     "rooms": [{"type": "Guest Room", "price": 380_000, "size": "26m²", "occupancy": 2, "count": 55, "perks": ["City view", "Gym"]}]},
    {"id": "h-par-1", "name": "Hôtel Eiffel Seine", "city": "Paris", "country": "France", "stars": 3, "rating": 4.0, "reviews": 1240, "area": "15th arrondissement", "cover": "paris-eiffel",
     "rooms": [{"type": "Classic Double", "price": 220_000, "size": "18m²", "occupancy": 2, "count": 30, "perks": ["Eiffel view", "Breakfast"]}]},
    {"id": "h-nbo-1", "name": "Sarova Stanley", "city": "Nairobi", "country": "Kenya", "stars": 5, "rating": 4.4, "reviews": 1560, "area": "Kimathi Street", "cover": "nairobi-park",
     "rooms": [{"type": "Heritage Room", "price": 130_000, "size": "30m²", "occupancy": 2, "count": 40, "perks": ["Breakfast", "Pool"]}]},
]
HOTEL_CITIES = sorted({h["city"] for h in HOTELS})

def get_hotel(hotel_id: str) -> dict | None:
    return next((h for h in HOTELS if h["id"] == hotel_id), None)

def hotel_rooms_available(conn, hotel_id: str, room_type: str, checkin: date, checkout: date) -> int:
    hotel = get_hotel(hotel_id)
    room = next((r for r in hotel["rooms"] if r["type"] == room_type), None) if hotel else None
    if not room:
        return 0
    rows = conn.execute(
        """SELECT COALESCE(SUM(CAST(json_extract(details, '$.rooms') AS INTEGER)),0) AS taken
           FROM bookings WHERE type='hotel' AND status IN ('pending','confirmed')
             AND json_extract(details,'$.hotel_id') = ?
             AND json_extract(details,'$.room_type') = ?
             AND date(json_extract(details,'$.checkin')) < ?
             AND date(json_extract(details,'$.checkout')) > ?""",
        (hotel_id, room_type, checkout.isoformat(), checkin.isoformat())).fetchone()
    return max(room["count"] - rows["taken"], 0)

def price_hotel(hotel_id: str, room_type: str, checkin: date, checkout: date, rooms: int) -> dict | None:
    hotel = get_hotel(hotel_id)
    room = next((r for r in hotel["rooms"] if r["type"] == room_type), None) if hotel else None
    if not room:
        return None
    nights = (checkout - checkin).days
    rate = ghs(room["price"])
    subtotal = rate * nights * rooms
    vat = round(subtotal * VAT)
    return {"nights": nights, "rooms": rooms, "rate_per_night": rate,
            "subtotal": subtotal, "vat": vat, "total": subtotal + vat}

# ----------------------------------------------------------------- cars
CAR_SUPPLIERS = ["Brother'sTrust Fleet", "Avis", "Hertz", "Europcar", "Keddy by Europcar"]
CAR_CATEGORIES = [
    {"code": "economy", "name": "Economy", "examples": "Toyota Corolla, Honda Civic", "seats": 5, "bags": 2, "transmission": "Automatic", "daily": 35_000},
    {"code": "compact_suv", "name": "Compact SUV", "examples": "Toyota RAV4, Honda CR-V", "seats": 5, "bags": 3, "transmission": "Automatic", "daily": 55_000},
    {"code": "premium", "name": "Premium Sedan", "examples": "Mercedes C-Class, BMW 3 Series", "seats": 5, "bags": 3, "transmission": "Automatic", "daily": 85_000},
    {"code": "luxury_suv", "name": "Luxury SUV", "examples": "Range Rover Evoque, Lexus RX", "seats": 5, "bags": 4, "transmission": "Automatic", "daily": 150_000},
    {"code": "van", "name": "7-Seater Van", "examples": "Toyota Hiace, Kia Carnival", "seats": 7, "bags": 6, "transmission": "Automatic", "daily": 95_000},
    {"code": "convertible", "name": "Convertible", "examples": "Ford Mustang, BMW 4 Series Cabrio", "seats": 4, "bags": 2, "transmission": "Automatic", "daily": 190_000},
]
CAR_CITIES = {
    "Lagos":        {"units": 6, "rates": {"convertible": 210_000}},
    "Abuja":        {"units": 5, "rates": {}},
    "Accra":        {"units": 4, "rates": {}},
    "Dubai":        {"units": 6, "rates": {"convertible": 230_000}},
    "London":       {"units": 5, "rates": {"economy": 55_000}},
    "Johannesburg": {"units": 4, "rates": {}},
    "Nairobi":      {"units": 4, "rates": {}},
}

def car_rate(city: str, category_code: str) -> int:
    cat = next(c for c in CAR_CATEGORIES if c["code"] == category_code)
    return ghs(CAR_CITIES[city]["rates"].get(category_code, cat["daily"]))

def cars_available(conn, city: str, category_code: str, pickup: date, ret: date) -> int:
    units = CAR_CITIES[city]["units"]
    rows = conn.execute(
        """SELECT COUNT(*) AS taken FROM bookings WHERE type='car' AND status IN ('pending','confirmed')
             AND json_extract(details,'$.city') = ?
             AND json_extract(details,'$.category') = ?
             AND date(json_extract(details,'$.pickup_date')) < ?
             AND date(json_extract(details,'$.return_date')) > ?""",
        (city, category_code, ret.isoformat(), pickup.isoformat())).fetchone()
    # each booking takes one unit for the whole range; conservative overlap count
    return max(units - rows["taken"], 0)

def price_car(city: str, category_code: str, pickup: date, ret: date) -> dict:
    days = (ret - pickup).days
    rate = car_rate(city, category_code)
    subtotal = rate * days
    vat = round(subtotal * VAT)
    return {"days": days, "daily_rate": rate, "subtotal": subtotal, "vat": vat, "total": subtotal + vat}

# ----------------------------------------------------------------- visa
VISA_COUNTRIES = [
    {"code": "AE", "name": "United Arab Emirates (Dubai & Abu Dhabi)", "flag": "", "category": "employment", "fee": 1500,
     "types": ["Visit / Tourist", "Employment (work permit)"],
     "processing": "5-10 working days (employment: 2-4 weeks)", "validity": "2 years (employment)", "stay": "Per contract",
     "docs": ["Passport bio-data page (6+ months validity)", "Passport photograph (white background)", "CV / résumé", "Educational & professional certificates", "Employment contract or job offer (work visa)"],
     "centers": ["Brother'sTrust HQ - Accra (Airport Residential)", "Brother'sTrust Office - Kumasi"],
     "note": "Direct employment to Dubai & Abu Dhabi through our licensed UAE partners. Visit visas also available for tourism and business."},
    {"code": "SA", "name": "Saudi Arabia", "flag": "", "category": "employment", "fee": 1300,
     "types": ["Employment (work visa)", "Umrah & Visit"],
     "processing": "2-6 weeks", "validity": "Per contract", "stay": "Per contract",
     "docs": ["Passport (6+ months validity)", "Passport photographs", "CV / résumé", "Educational & professional certificates", "Employment contract (work visa)"],
     "centers": ["Brother'sTrust HQ - Accra (Airport Residential)", "Brother'sTrust Office - Kumasi"],
     "note": "Work visas processed through employer sponsorship, plus Umrah and visit packages."},
    {"code": "KW", "name": "Kuwait", "flag": "", "category": "employment", "fee": 1400,
     "types": ["Employment (work visa)"],
     "processing": "3-8 weeks", "validity": "Per contract", "stay": "Per contract",
     "docs": ["Passport (6+ months validity)", "Passport photographs", "CV / résumé", "Educational certificates (attested)", "Employment contract"],
     "centers": ["Brother'sTrust HQ - Accra (Airport Residential)", "Brother'sTrust Office - Kumasi"],
     "note": "Direct employment with Kuwaiti employers. We handle attestation, medicals and embassy submission."},
    {"code": "QA", "name": "Qatar", "flag": "", "category": "employment", "fee": 1200,
     "types": ["Employment (work visa)", "Visit"],
     "processing": "2-4 weeks", "validity": "Per contract", "stay": "Per contract",
     "docs": ["Passport (6+ months validity)", "Passport photographs", "CV / résumé", "Educational & professional certificates", "Employment contract (work visa)"],
     "centers": ["Brother'sTrust HQ - Accra (Airport Residential)", "Brother'sTrust Office - Kumasi"],
     "note": "Work visas with leading Qatari employers, plus family-visit and tourist visas."},
    {"code": "GB", "name": "United Kingdom", "flag": "", "category": "embassy", "fee": 1900,
     "types": ["Visit", "Business", "Work (employer-sponsored)"],
     "processing": "15 working days", "validity": "6 months - 5 years", "stay": "Up to 180 days per visit",
     "docs": ["Passport (6+ months validity, 2 blank pages)", "Bank statements (6 months)", "Employment letter or business registration", "Travel itinerary & accommodation", "TB test certificate (work visa)"],
     "centers": ["UK Visas & Immigration - Accra"],
     "note": "Visitor, business and employer-sponsored work routes (Skilled Worker). Biometrics at the Accra VAC."},
    {"code": "DK", "name": "Denmark", "flag": "", "category": "vfs", "fee": 1400,
     "types": ["Visit", "Employment (Danish work & residence permit)"],
     "processing": "15-30 days", "validity": "Up to 90 days (visit)", "stay": "90 days in 180 (visit)",
     "docs": ["Passport (issued < 10 years ago, 6+ months validity)", "Bank statements (6 months)", "Travel insurance (\u20ac30,000 cover)", "Employment contract or job offer (work permit)", "Educational certificates"],
     "centers": ["VFS Global - Accra"],
     "note": "Schengen visits and Danish employment permits through employer sponsorship. We prepare your full application pack."},
    {"code": "BE", "name": "Belgium", "flag": "", "category": "vfs", "fee": 1300,
     "types": ["Visit", "Business", "Employment (single permit)"],
     "processing": "15 calendar days (visit)", "validity": "Up to 90 days", "stay": "90 days in 180",
     "docs": ["Passport (6+ months validity)", "Bank statements (6 months)", "Travel insurance (\u20ac30,000 cover)", "Flight & hotel reservations", "Single-permit work authorisation (employment)"],
     "centers": ["VFS Global - Accra"],
     "note": "Schengen visit/business visas and Belgian single-permit employment through accredited employers."},
    {"code": "RO", "name": "Romania", "flag": "", "category": "embassy", "fee": 900,
     "types": ["Employment (D visa)", "Visit"],
     "processing": "10-20 working days", "validity": "90 days (D visa)", "stay": "Long-term (employment)",
     "docs": ["Passport (6+ months validity)", "Passport photographs", "Employment contract (D visa)", "Criminal record certificate", "Medical certificate"],
     "centers": ["Embassy of Romania, Accra"],
     "note": "Fast-growing destination for Ghanaian professionals — employment D visas with verified employers."},
    {"code": "RS", "name": "Serbia", "flag": "", "category": "employment", "fee": 700,
     "types": ["Employment (work permit)", "Visit"],
     "processing": "3-6 weeks", "validity": "Per work permit", "stay": "Per contract",
     "docs": ["Passport (6+ months validity)", "Passport photographs", "CV / résumé", "Employment contract or work-permit approval", "Educational certificates"],
     "centers": ["Brother'sTrust HQ - Accra (Airport Residential)", "Brother'sTrust Office - Kumasi"],
     "note": "Employment with Serbian employers in manufacturing, logistics and hospitality. Work permit filed by the employer."},
    {"code": "US", "name": "United States", "flag": "", "category": "embassy", "fee": 2800,
     "types": ["Visit (B1/B2)", "Business", "Employment (employer-sponsored)"],
     "processing": "2 days - several weeks (interview)", "validity": "Up to 10 years (B1/B2)", "stay": "180 days per visit",
     "docs": ["Passport (6+ months beyond stay)", "DS-160 confirmation page", "Bank statements (6 months)", "Employment/business documents", "Petition approval notice (employment visas)"],
     "centers": ["U.S. Embassy Accra"],
     "note": "Visit and business visas plus employer-sponsored employment categories (H, L, O, EB). Interview in Accra — book early."},
    {"code": "CA", "name": "Canada", "flag": "", "category": "embassy", "fee": 2200,
     "types": ["Visit (TRV)", "Business", "Work Permit (employer-sponsored)"],
     "processing": "2-8 weeks", "validity": "Up to 10 years (TRV)", "stay": "Up to 6 months per visit",
     "docs": ["Passport (6+ months validity)", "Bank statements (6 months)", "Employment letter / business documents", "Invitation letter (business)", "LMIA or job offer (work permit)"],
     "centers": ["Canada Visa Application Centre - Accra"],
     "note": "Visitor and business visas plus employer-sponsored work permits. Biometrics at the Accra VAC."},
    {"code": "NG", "name": "Nigeria", "flag": "", "category": "visa_free", "fee": 0,
     "types": ["ECOWAS visa-free travel"],
     "processing": "Instant (ECOWAS)", "validity": "90 days", "stay": "90 days",
     "docs": ["Valid Ghanaian passport (6+ months validity)", "Ghana Card accepted for ECOWAS travel"],
     "note": "Ghanaians enjoy visa-free entry to Nigeria under ECOWAS protocols. We can still arrange your flights and hotels."},
    {"code": "KE", "name": "Kenya", "flag": "", "category": "evisa", "fee": 750,
     "types": ["Visit / Tourist"],
     "processing": "3-5 working days", "validity": "90 days", "stay": "90 days",
     "docs": ["Passport bio-data page (6+ months validity)", "Passport photograph", "Return flight itinerary", "Hotel reservation"],
     "note": "Kenya eTA issued electronically before departure — apply at least 3 days before travel."},
]

def get_country(code: str) -> dict | None:
    return next((c for c in VISA_COUNTRIES if c["code"] == code.upper()), None)

SLOT_TIMES = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00"]

def ensure_slots(conn, country: str, center: str, start: date, days: int = 21) -> None:
    """Pre-create visa appointment slots for the next `days` business days."""
    for i in range(days):
        d = start + timedelta(days=i)
        if d.weekday() >= 5:            # skip weekends
            continue
        cap = 3 + int(hashlib.sha1(f"{country}{center}{d.isoformat()}".encode()).hexdigest()[:2], 16) % 4
        for t in SLOT_TIMES:
            conn.execute(
                """INSERT INTO visa_slots (country, center, date, time, capacity)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(country, center, date, time) DO NOTHING""",
                (country, center, d.isoformat(), t, cap))

def slots_for(conn, country: str, center: str, from_date: date) -> list[dict]:
    ensure_slots(conn, country, center, from_date)
    rows = conn.execute(
        """SELECT * FROM visa_slots WHERE country=? AND center=? AND date>=? AND date<?
           ORDER BY date, time""",
        (country, center, from_date.isoformat(), (from_date + timedelta(days=21)).isoformat())).fetchall()
    return [{"date": r["date"], "time": r["time"], "capacity": r["capacity"],
             "booked": r["booked"], "available": r["capacity"] - r["booked"]} for r in rows]

def price_visa(country_code: str, applicants: int) -> dict | None:
    c = get_country(country_code)
    if not c:
        return None
    fee = c["fee"]  # stored in GH¢
    fees = fee * applicants
    total = fees + (SERVICE_FEE if c["category"] != "visa_free" else 0)
    return {"country": c["name"], "applicants": applicants, "visa_fee": fee,
            "service_fee": SERVICE_FEE if c["category"] != "visa_free" else 0,
            "total": total}
