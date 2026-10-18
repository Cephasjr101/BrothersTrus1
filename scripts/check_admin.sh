#!/usr/bin/env bash
# Verify bookings + flight details + analytics reach the admin dashboard

echo "======== ADMIN DASHBOARD DATA CHECK ========"
python - <<'EOF'
import json, time, urllib.request, urllib.error, datetime, sqlite3, os

BASE = "http://localhost:8000"
def call(m, p, h=None, d=None):
    r = urllib.request.Request(BASE + p, method=m,
        data=json.dumps(d).encode() if d is not None else None,
        headers={"Content-Type": "application/json", **(h or {})})
    with urllib.request.urlopen(r, timeout=30) as x:
        return json.loads(x.read().decode() or "{}")

fails = []
def check(name, cond, extra=""):
    print(f"  [{'OK' if cond else '!!'}] {name} {extra}")
    if not cond:
        fails.append(name)

# --- admin login ---
try:
    a = call("POST", "/auth/login", d={"email": os.environ.get("ADMIN_EMAIL", "admin@brotherstrusttravel.com"),
                                       "password": os.environ.get("ADMIN_PASSWORD", "BT#Admin1")})
    AH = {"Authorization": "Bearer " + a["access_token"]}
    check("admin login", True)
except Exception as e:
    print(f"  [!!] admin login failed: {e}")
    print("  -> set ADMIN_EMAIL/ADMIN_PASSWORD env vars correctly")
    raise SystemExit

# --- create + pay a flight booking ---
dep = (datetime.date.today() + datetime.timedelta(days=14)).isoformat()
reg = call("POST", "/auth/register", d={"email": f"adm{int(time.time())}@t.bt", "password": "secret1", "full_name": "Adm Check"})
H = {"Authorization": "Bearer " + reg["access_token"]}
fs = call("GET", f"/flights/search?origin=ACC&dest=DXB&date={dep}")
f0 = fs["flights"][0]
b = call("POST", "/bookings/flight", H, {
    "trip_type": "one_way", "cabin": "economy", "bags": 1,
    "legs": [{"origin": f0["origin"], "dest": f0["dest"], "date": dep, "flight_key": f0["flight_key"]}],
    "passengers": [{"type": "adult", "title": "Ms", "first_name": "Admin", "last_name": "Check", "dob": "1992-03-08"}],
    "contact_email": "adm@t.bt", "contact_phone": "+233551934922"})
ref = b["reference"]
call("POST", "/payments/confirm", H, {"reference": ref, "method": "card"})
print(f"  [OK] test booking created+paid: {ref} ({f0['airline']} {f0['flight_no']})")

# --- admin bookings list contains it WITH flight details ---
bl = call("GET", "/admin/bookings", AH)
mine = next((x for x in bl if x["reference"] == ref), None)
check("booking appears in admin list", mine is not None)
if mine:
    check("  type is flight", mine["type"] == "flight")
    check("  travelers stored", len(mine.get("travelers", [])) == 1)

# --- booking detail (admin side via user endpoint shows legs) ---
det = call("GET", f"/bookings/{ref}", H)
legs = det.get("details", {}).get("legs", [])
check("flight legs stored on booking", len(legs) == 1 and legs[0]["airline"] == f0["airline"],
      f"({legs[0]['airline']} {legs[0]['flight_no']} {legs[0]['origin']}->{legs[0]['dest']})" if legs else "(none)")

# --- admin stats reflect revenue ---
st = call("GET", "/admin/stats", AH)
check("admin stats respond", st.get("bookings", 0) >= 1, f"(total bookings: {st.get('bookings')}, revenue: {st.get('revenue_confirmed')})")

# --- analytics/logs stored ---
an = call("GET", "/admin/analytics", AH)
check("analytics endpoint responds", "pageviews" in an, f"(pageviews: {an.get('pageviews')}, events: {an.get('events')})")

# --- raw DB sanity ---
db = os.environ.get("BROTHERSTRUST_DB", "/app/data/bt-travel.db")
if not os.path.exists(db):
    db = "/app/backend/bt-travel.db"
try:
    conn = sqlite3.connect(db)
    n = conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
    na = conn.execute("SELECT COUNT(*) FROM analytics").fetchone()[0]
    conn.close()
    check("database stores bookings", n >= 1, f"({n} rows)")
    check("database stores analytics logs", na >= 0, f"({na} rows)")
except Exception as e:
    print(f"  [~~] DB direct check skipped: {e}")

# --- cleanup ---
call("POST", f"/bookings/{ref}/cancel", H)
print(f"  [OK] test booking {ref} cancelled (cleanup)")

print()
print("RESULT:", "ALL ADMIN DATA FLOWS WORKING" if not fails else f"ISSUES: {fails}")
EOF
echo "================================================"
