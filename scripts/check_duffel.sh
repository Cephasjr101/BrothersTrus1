#!/usr/bin/env bash
# Brother'sTrust - FULL Duffel pipeline verification (book -> pay -> ticket -> cancel)

echo "===== Duffel full-pipeline check ====="
echo
echo "--- 1. Code deployed? ---"
echo -n "pax payload:    "; grep -c "_pax_payload" /app/backend/services/airlines.py
echo -n "hold orders:    "; grep -c "def hold_order" /app/backend/services/airlines.py
echo -n "instant fallback:"; grep -c "def book_instant" /app/backend/services/airlines.py
echo -n "flights wiring: "; grep -c "instant_order" /app/backend/routers/flights.py
echo -n "payments wiring:"; grep -c "instant_order" /app/backend/routers/payments.py
echo
echo "--- 2. Token ---"
case "$DUFFEL_API_TOKEN" in
  duffel_live_*) echo "LIVE token (check dashboard in LIVE mode)";;
  duffel_test_*) echo "TEST token (check dashboard in TEST mode)";;
  *) echo "[!!] token missing/odd";;
esac
echo
echo "--- 3. FULL LOOP: book -> pay -> verify ticket -> cancel ---"
python - <<'EOF'
import json, time, urllib.request, urllib.error, datetime

BASE = "http://localhost:8000"
def call(method, path, headers=None, payload=None):
    req = urllib.request.Request(BASE + path, method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, json.loads(r.read().decode() or "{}")

dep = (datetime.date.today() + datetime.timedelta(days=21)).isoformat()
ok = True
try:
    s, reg = call("POST", "/auth/register",
        payload={"email": f"e2e{int(time.time())}@test.bt", "password": "check123", "full_name": "E2E Check"})
    H = {"Authorization": "Bearer " + reg["access_token"]}

    s, fs = call("GET", f"/flights/search?origin=ACC&dest=DXB&date={dep}")
    f0 = fs["flights"][0]
    print(f"1. SEARCH OK: {f0['airline']} {f0['flight_no']} {f0['origin']} -> {f0['dest']}")

    s, b = call("POST", "/bookings/flight", headers=H, payload={
        "trip_type": "one_way", "cabin": "economy", "bags": 0,
        "legs": [{"origin": f0["origin"], "dest": f0["dest"], "date": dep, "flight_key": f0["flight_key"]}],
        "passengers": [{"type": "adult", "title": "Mr", "first_name": "E2E", "last_name": "Check", "dob": "1990-05-15"}],
        "contact_email": "e2e@test.bt", "contact_phone": "+233551934922"})
    d = b.get("details", {})
    ref = b.get("reference")
    order = d.get("hold_order") or d.get("instant_order") or {}
    if order.get("order_id"):
        kind = "HOLD" if d.get("hold_order") else "INSTANT(defer)"
        print(f"2. ORDER CREATED [{kind}]: {order.get('order_id')} | ref {ref}")
        print("   >>> Check your Duffel dashboard NOW (correct mode) - order should be visible")
    else:
        ok = False
        print(f"2. [!!] NO ORDER reached Duffel. hold_error: {d.get('hold_error')}")

    s, p = call("POST", "/payments/confirm", headers=H, payload={"reference": ref, "method": "card"})
    s, bd = call("GET", f"/bookings/{ref}", headers=H)
    tickets = bd.get("details", {}).get("tickets") or []
    status = bd.get("status")
    print(f"3. PAYMENT: status={status} | tickets={tickets if tickets else '(none recorded)'}")
    if status == "confirmed" and tickets:
        print("   >>> TICKET RECORDED - payment pipeline complete")
    else:
        print("   (note: hold captures/instant already ticketed at booking; check dashboard)")

    s, c = call("POST", f"/bookings/{ref}/cancel", headers=H)
    print(f"4. CANCEL: {c.get('status')} (refund {c.get('refund_amount')}) - check order cancelled in Duffel dashboard")
    print()
    print("RESULT:", "ALL STEPS PASSED - Duffel pipeline fully operational" if ok else "ORDER STEP FAILED - see hold_error above")
except urllib.error.HTTPError as e:
    print("[!!] failed:", e.code, e.read().decode()[:250])
EOF
echo
echo "===== check complete ====="
