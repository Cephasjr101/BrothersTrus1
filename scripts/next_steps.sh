#!/usr/bin/env bash
# Brother'sTrust / JapaFly - "What do I do next?" wizard
# Checks every component and prints your prioritized action list.

TODO=()
ok()   { echo "  [OK] $1"; }
miss() { echo "  [!!] $1"; TODO+=("$2"); }

echo "================  JAPAFLY SETUP WIZARD  ================"

echo
echo "== 1. DUFFEL (flights) =="
echo -n "  code (pax/linking/balance): "
n1=$(grep -c "_pax_payload" /app/backend/services/airlines.py); n2=$(grep -c "pax_id" /app/backend/routers/flights.py)
if [ "$n1" -ge 3 ] && [ "$n2" -ge 2 ]; then ok "deployed ($n1/$n2)"; else miss "stale code" "Re-upload backend/services/airlines.py + backend/routers/flights.py"; fi
case "$DUFFEL_API_TOKEN" in
  duffel_live_*) ok "LIVE token";;
  duffel_test_*) ok "TEST token";;
  *) miss "token missing" "Add DUFFEL_API_TOKEN in Render Environment";;
esac
python - <<'EOF'
import os, json, urllib.request
try:
    tok = os.environ["DUFFEL_API_TOKEN"]
    req = urllib.request.Request("https://api.duffel.com/air/airlines",
        headers={"Authorization": "Bearer " + tok, "Duffel-Version": "v2"})
    with urllib.request.urlopen(req, timeout=15) as r:
        print("  [OK] Duffel accepts token - LIVE mode bookings ready once wallet is funded")
except Exception as e:
    print(f"  [!!] Duffel token problem: {e}")
EOF
miss "wallet" "TOP UP Duffel wallet (Dashboard > Payments > Balance, $100+) OR get deferred terms from support"

echo
echo "== 2. PAYSTACK (customer payments) =="
case "$PAYSTACK_SECRET_KEY" in
  sk_live*) ok "LIVE key set - real money mode";;
  sk_test*) ok "TEST key only" "Swap to LIVE Paystack key (sk_live_...) when ready for real payments";;
  *) miss "not set" "Add PAYSTACK_SECRET_KEY (sk_live_... for real money)";;
esac

echo
echo "== 3. LITEAPI (hotels) =="
if [ -n "$LITEAPI_KEY" ]; then ok "key set"; else miss "missing" "Add LITEAPI_KEY (dashboard.liteapi.travel - sandbox key)"; fi

echo
echo "== 4. FIREBASE (Google login) =="
if [ -n "$FIREBASE_API_KEY" ] && [ -n "$FIREBASE_PROJECT_ID" ]; then
  ok "vars set"
  python - <<'EOF'
import urllib.request
try:
    body = urllib.request.urlopen("http://localhost:8000/auth/firebase-config", timeout=10).read().decode()
    if '"apiKey"' in body:
        print("  [OK] config endpoint serving - Google login should work (test on site)")
    else:
        print("  [!!] endpoint not serving config")
except Exception as e:
    print(f"  [!!] {e}")
EOF
else
  miss "vars incomplete" "Set FIREBASE_API_KEY + FIREBASE_PROJECT_ID (+ AUTH_DOMAIN, APP_ID)"
fi

echo
echo "== 5. NOTIFICATIONS =="
[ -n "$SENDGRID_API_KEY" ] && ok "SendGrid set (emails on)" || miss "no SendGrid" "Add SENDGRID_API_KEY for booking emails"
[ -n "$AT_API_KEY" ] && ok "Africa's Talking set (SMS on)" || echo "  [~~] no Africa's Talking (optional - SMS updates off)"

echo
echo "== 6. PRICING =="
[ -n "$MARKUP_PERCENT" ] && ok "markup ${MARKUP_PERCENT}%" || miss "MARKUP_PERCENT unset" "Add MARKUP_PERCENT=8 in Render (your commission!)"
[ -n "$USD_GHS_RATE" ] && ok "FX rate ${USD_GHS_RATE}" || echo "  [~~] USD_GHS_RATE unset (auto-fetching - set Absa rate daily for control)"

echo
echo "== 7. DOMAIN (japafly.com) =="
python - <<'EOF'
import urllib.request
try:
    body = urllib.request.urlopen("https://www.japafly.com/api/health", timeout=15).read().decode()
    if '"ok": true' in body or '"ok":true' in body:
        print("  [OK] www.japafly.com is LIVE and serving this app!")
    else:
        print("  [~~] japafly.com responds but unexpected content")
except Exception as e:
    print(f"  [!!] www.japafly.com not reachable yet: {type(e).__name__}")
    print("       -> Set DNS at registrar + add domain in Render > Custom Domains")
EOF

echo
echo "== 8. SECURITY =="
[ "$BROTHERSTRUST_SECRET" = "dev-only-secret-change-me" ] || [ -z "$BROTHERSTRUST_SECRET" ] \
  && miss "dev secret" "Set BROTHERSTRUST_SECRET (long random string)" || ok "custom secret"

echo
echo "================  YOUR NEXT ACTIONS  ================"
if [ ${#TODO[@]} -eq 0 ]; then
  echo "  ALL CHECKS PASSED - do the real-money smoke test:"
  echo "  1. Book cheapest flight on site -> pay with your own MoMo"
  echo "  2. Verify: Paystack settles -> Duffel order ticketed -> email arrives"
  echo "  3. Put japafly.com in your TikTok/Instagram bio - you're open for business"
else
  i=1
  for t in "${TODO[@]}"; do echo "  $i. $t"; i=$((i+1)); done
fi
echo "====================================================="
