# World airport & city reference data for destination search (code, city, country).
# The 12 "home" airports keep full detail in services/airlines.py; these extend
# the search form to the whole world when a live provider (Duffel) is active.
WORLD_AIRPORTS = [
    # ---- West Africa
    ("ACC", "Accra", "Ghana"), ("KMS", "Kumasi", "Ghana"), ("TML", "Tamale", "Ghana"),
    ("TKD", "Takoradi", "Ghana"), ("NYI", "Sunyani", "Ghana"),
    ("LOS", "Lagos", "Nigeria"), ("ABV", "Abuja", "Nigeria"), ("PHC", "Port Harcourt", "Nigeria"),
    ("KAN", "Kano", "Nigeria"), ("KAD", "Kaduna", "Nigeria"), ("ENU", "Enugu", "Nigeria"),
    ("BNI", "Benin City", "Nigeria"), ("ILR", "Ilorin", "Nigeria"), ("JOS", "Jos", "Nigeria"),
    ("COO", "Cotonou", "Benin"), ("LFW", "Lome", "Togo"), ("OUA", "Ouagadougou", "Burkina Faso"),
    ("BKO", "Bamako", "Mali"), ("DKR", "Dakar", "Senegal"), ("ABJ", "Abidjan", "Ivory Coast"),
    ("FNA", "Freetown", "Sierra Leone"), ("MLW", "Monrovia", "Liberia"), ("CKY", "Conakry", "Guinea"),
    ("OXB", "Bissau", "Guinea-Bissau"), ("BAN", "Banjul", "Gambia"), ("NIM", "Niamey", "Niger"),
    ("NDJ", "N'Djamena", "Chad"), ("BGF", "Bangui", "CAR"), ("DLA", "Douala", "Cameroon"),
    ("NSI", "Yaounde", "Cameroon"), ("SSG", "Malabo", "Equatorial Guinea"), ("LBV", "Libreville", "Gabon"),
    ("BZV", "Brazzaville", "Congo"), ("FIH", "Kinshasa", "DR Congo"),
    # ---- East & Southern Africa
    ("NBO", "Nairobi", "Kenya"), ("MBA", "Mombasa", "Kenya"), ("EBB", "Entebbe", "Uganda"),
    ("DAR", "Dar es Salaam", "Tanzania"), ("ZNZ", "Zanzibar", "Tanzania"), ("JRO", "Kilimanjaro", "Tanzania"),
    ("KGL", "Kigali", "Rwanda"), ("BJM", "Bujumbura", "Burundi"), ("ADD", "Addis Ababa", "Ethiopia"),
    ("ASM", "Asmara", "Eritrea"), ("JUB", "Juba", "South Sudan"), ("KRT", "Khartoum", "Sudan"),
    ("JNB", "Johannesburg", "South Africa"), ("CPT", "Cape Town", "South Africa"), ("DUR", "Durban", "South Africa"),
    ("GBE", "Gaborone", "Botswana"), ("WDH", "Windhoek", "Namibia"), ("LAD", "Luanda", "Angola"),
    ("MPM", "Maputo", "Mozambique"), ("LUN", "Lusaka", "Zambia"), ("HRE", "Harare", "Zimbabwe"),
    ("LLW", "Lilongwe", "Malawi"), ("TNR", "Antananarivo", "Madagascar"), ("MRU", "Mauritius", "Mauritius"),
    ("SEZ", "Seychelles", "Seychelles"),
    # ---- North Africa
    ("CAI", "Cairo", "Egypt"), ("HRG", "Hurghada", "Egypt"), ("SSH", "Sharm El Sheikh", "Egypt"),
    ("ALY", "Alexandria", "Egypt"), ("TUN", "Tunis", "Tunisia"), ("NBE", "Enfidha", "Tunisia"),
    ("ALG", "Algiers", "Algeria"), ("ORN", "Oran", "Algeria"), ("CMN", "Casablanca", "Morocco"),
    ("RAK", "Marrakech", "Morocco"), ("TNG", "Tangier", "Morocco"), ("AGA", "Agadir", "Morocco"),
    ("TIP", "Tripoli", "Libya"),
    # ---- Europe
    ("LHR", "London Heathrow", "United Kingdom"), ("LGW", "London Gatwick", "United Kingdom"),
    ("STN", "London Stansted", "United Kingdom"), ("MAN", "Manchester", "United Kingdom"),
    ("BHX", "Birmingham", "United Kingdom"), ("EDI", "Edinburgh", "United Kingdom"),
    ("GLA", "Glasgow", "United Kingdom"), ("DUB", "Dublin", "Ireland"), ("SNN", "Shannon", "Ireland"),
    ("CDG", "Paris Charles de Gaulle", "France"), ("ORY", "Paris Orly", "France"),
    ("NCE", "Nice", "France"), ("LYS", "Lyon", "France"), ("MRS", "Marseille", "France"),
    ("AMS", "Amsterdam", "Netherlands"), ("FRA", "Frankfurt", "Germany"), ("MUC", "Munich", "Germany"),
    ("BER", "Berlin", "Germany"), ("DUS", "Dusseldorf", "Germany"), ("HAM", "Hamburg", "Germany"),
    ("ZRH", "Zurich", "Switzerland"), ("GVA", "Geneva", "Switzerland"), ("MAD", "Madrid", "Spain"),
    ("BCN", "Barcelona", "Spain"), ("AGP", "Malaga", "Spain"), ("PMI", "Palma de Mallorca", "Spain"),
    ("LIS", "Lisbon", "Portugal"), ("OPO", "Porto", "Portugal"), ("FAO", "Faro", "Portugal"),
    ("FCO", "Rome Fiumicino", "Italy"), ("MXP", "Milan Malpensa", "Italy"), ("VCE", "Venice", "Italy"),
    ("NAP", "Naples", "Italy"), ("VIE", "Vienna", "Austria"), ("PRG", "Prague", "Czech Republic"),
    ("BUD", "Budapest", "Hungary"), ("WAW", "Warsaw", "Poland"), ("KRK", "Krakow", "Poland"),
    ("CPH", "Copenhagen", "Denmark"), ("BLL", "Billund", "Denmark"), ("ARN", "Stockholm", "Sweden"),
    ("GOT", "Gothenburg", "Sweden"), ("OSL", "Oslo", "Norway"), ("BGO", "Bergen", "Norway"),
    ("HEL", "Helsinki", "Finland"), ("KEF", "Reykjavik", "Iceland"), ("ATH", "Athens", "Greece"),
    ("SKG", "Thessaloniki", "Greece"), ("IST", "Istanbul", "Türkiye"), ("SAW", "Istanbul Sabiha", "Türkiye"),
    ("AYT", "Antalya", "Türkiye"), ("BEG", "Belgrade", "Serbia"), ("ZAG", "Zagreb", "Croatia"),
    ("SPU", "Split", "Croatia"), ("LJU", "Ljubljana", "Slovenia"), ("BTS", "Bratislava", "Slovakia"),
    ("OTP", "Bucharest", "Romania"), ("CLJ", "Cluj-Napoca", "Romania"), ("SOF", "Sofia", "Bulgaria"),
    ("TIA", "Tirana", "Albania"), ("SKP", "Skopje", "North Macedonia"), ("PRN", "Pristina", "Kosovo"),
    ("TLL", "Tallinn", "Estonia"), ("RIX", "Riga", "Latvia"), ("VNO", "Vilnius", "Lithuania"),
    ("MLA", "Malta", "Malta"),
    # ---- Middle East
    ("DXB", "Dubai", "UAE"), ("AUH", "Abu Dhabi", "UAE"), ("SHJ", "Sharjah", "UAE"),
    ("DOH", "Doha", "Qatar"), ("JED", "Jeddah", "Saudi Arabia"), ("RUH", "Riyadh", "Saudi Arabia"),
    ("DMM", "Dammam", "Saudi Arabia"), ("MED", "Medina", "Saudi Arabia"), ("KWI", "Kuwait City", "Kuwait"),
    ("BAH", "Manama", "Bahrain"), ("MCT", "Muscat", "Oman"), ("AMM", "Amman", "Jordan"),
    ("BEY", "Beirut", "Lebanon"), ("BGW", "Baghdad", "Iraq"), ("EBL", "Erbil", "Iraq"),
    # ---- Asia
    ("SIN", "Singapore", "Singapore"), ("KUL", "Kuala Lumpur", "Malaysia"), ("PEN", "Penang", "Malaysia"),
    ("BKK", "Bangkok", "Thailand"), ("DMK", "Bangkok Don Mueang", "Thailand"), ("CNX", "Chiang Mai", "Thailand"),
    ("HKT", "Phuket", "Thailand"), ("CGK", "Jakarta", "Indonesia"), ("DPS", "Bali", "Indonesia"),
    ("MNL", "Manila", "Philippines"), ("CEB", "Cebu", "Philippines"), ("SGN", "Ho Chi Minh City", "Vietnam"),
    ("HAN", "Hanoi", "Vietnam"), ("DAC", "Dhaka", "Bangladesh"), ("CMB", "Colombo", "Sri Lanka"),
    ("KHI", "Karachi", "Pakistan"), ("LHE", "Lahore", "Pakistan"), ("ISB", "Islamabad", "Pakistan"),
    ("DEL", "New Delhi", "India"), ("BOM", "Mumbai", "India"), ("BLR", "Bangalore", "India"),
    ("HYD", "Hyderabad", "India"), ("MAA", "Chennai", "India"), ("CCU", "Kolkata", "India"),
    ("GOI", "Goa", "India"), ("COK", "Kochi", "India"),
    ("HKG", "Hong Kong", "Hong Kong"), ("TPE", "Taipei", "Taiwan"), ("PEK", "Beijing", "China"),
    ("PVG", "Shanghai", "China"), ("CAN", "Guangzhou", "China"), ("SZX", "Shenzhen", "China"),
    ("ICN", "Seoul", "South Korea"), ("HND", "Tokyo Haneda", "Japan"), ("NRT", "Tokyo Narita", "Japan"),
    ("KIX", "Osaka", "Japan"),
    # ---- Americas
    ("JFK", "New York JFK", "USA"), ("EWR", "Newark", "USA"), ("LGA", "New York LaGuardia", "USA"),
    ("BOS", "Boston", "USA"), ("MIA", "Miami", "USA"), ("FLL", "Fort Lauderdale", "USA"),
    ("MCO", "Orlando", "USA"), ("ATL", "Atlanta", "USA"), ("CLT", "Charlotte", "USA"),
    ("IAD", "Washington DC", "USA"), ("DCA", "Washington Reagan", "USA"), ("ORD", "Chicago O'Hare", "USA"),
    ("DFW", "Dallas", "USA"), ("IAH", "Houston", "USA"), ("DEN", "Denver", "USA"),
    ("PHX", "Phoenix", "USA"), ("LAS", "Las Vegas", "USA"), ("LAX", "Los Angeles", "USA"),
    ("SFO", "San Francisco", "USA"), ("SEA", "Seattle", "USA"), ("PDX", "Portland", "USA"),
    ("MSP", "Minneapolis", "USA"), ("DTW", "Detroit", "USA"), ("YYZ", "Toronto", "Canada"),
    ("YUL", "Montreal", "Canada"), ("YVR", "Vancouver", "Canada"), ("MEX", "Mexico City", "Mexico"),
    ("CUN", "Cancun", "Mexico"), ("GDL", "Guadalajara", "Mexico"), ("BOG", "Bogota", "Colombia"),
    ("MDE", "Medellin", "Colombia"), ("LIM", "Lima", "Peru"), ("SCL", "Santiago", "Chile"),
    ("GRU", "Sao Paulo", "Brazil"), ("GIG", "Rio de Janeiro", "Brazil"), ("BSB", "Brasilia", "Brazil"),
    ("EZE", "Buenos Aires", "Argentina"), ("PTY", "Panama City", "Panama"), ("SJO", "San Jose", "Costa Rica"),
    ("HAV", "Havana", "Cuba"), ("SDQ", "Santo Domingo", "Dominican Republic"), ("MVD", "Montevideo", "Uruguay"),
    # ---- Oceania
    ("SYD", "Sydney", "Australia"), ("MEL", "Melbourne", "Australia"), ("BNE", "Brisbane", "Australia"),
    ("PER", "Perth", "Australia"), ("ADL", "Adelaide", "Australia"), ("AKL", "Auckland", "New Zealand"),
    ("WLG", "Wellington", "New Zealand"), ("CHC", "Christchurch", "New Zealand"), ("NAN", "Nadi", "Fiji"),
]


def world_airports() -> list[dict]:
    seen, out = set(), []
    for code, city, country in WORLD_AIRPORTS:
        if not code or not city or code in seen:
            continue
        seen.add(code)
        out.append({"code": code, "city": city, "country": country})
    return out


def world_cities() -> list[str]:
    return sorted({city for _, city, _ in WORLD_AIRPORTS if city} |
                  {"Kumasi", "Tamale", "Takoradi", "East Legon", "Osu", "Spintex", "Dubai Marina",
                   "Palm Jumeirah", "Deira", "Sharm El Sheikh", "Doha West Bay", "Makkah", "Madina"})
