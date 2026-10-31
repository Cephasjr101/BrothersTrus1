#!/usr/bin/env bash
# Payment integration check for japafly.com - no real money moves.
# Run in Git Bash:  bash check_payments.sh
BASE="https://japafly.com"
fails=0

say()  { echo; echo "== $1"; }
pass() { echo "   PASS - $1"; }
fail() { echo "   FAIL - $1"; fails=$((fails+1)); }

code() { curl -s -o /tmp/_resp -w "%{http_code}" "$@"; }
body() { cat /tmp/_resp; }

# 1. API alive ---------------------------------------------------------------
say "1. API health"
[ "$(code "$BASE/api/health")" = "200" ] && pass "API is up" || fail "API did not respond 200: $(body)"

# 2. Paystack key configured? (the critical one) ------------------------------
# Webhook with a bad signature: 401 = live mode with key set.
# 200 {"ok":true} = key MISSING (site running in fallback mode).
say "2. Paystack key / live mode"
c=$(code -X POST "$BASE/payments/webhook" -H "Content-Type: application/json" -d '{}')
if [ "$c" = "401" ]; then
  pass "PAYSTACK_SECRET_KEY is set - gateway is live"
elif [ "$c" = "200" ]; then
  fail "key NOT configured - running fallback mode. Set PAYSTACK_SECRET_KEY via: fly secrets set"
else
  fail "unexpected webhook response: HTTP $c: $(body)"
fi

# 3. Old demo/confirm endpoint must be gone -----------------------------------
say "3. Old demo endpoint removed"
c=$(code -X POST "$BASE/payments/confirm" -H "Content-Type: application/json" -d '{}')
if [ "$c" = "404" ] || [ "$c" = "405" ]; then
  pass "old /payments/confirm is gone (HTTP $c)"
else
  fail "old backend still serving /payments/confirm (HTTP $c)"
fi

# 4. Frontend is the live build (no demo checkout) -----------------------------
say "4. Frontend checkout code"
js=$(curl -s "$BASE/js/app.js?v=7")
if echo "$js" | grep -q "Demo gateway"; then
  fail "demo checkout still in app.js - deploy the new frontend"
elif echo "$js" | grep -q "Accra . Dubai"; then
  pass "live frontend deployed (demo code absent, new cards present)"
elif echo "$js" | grep -q "Demo gateway"; then
  fail "demo checkout still in app.js"
else
  pass "demo code absent (cards not found - check app.js version manually)"
fi

# 5. Full payment chain: register -> login -> initialize ----------------------
# A fake booking reference must give 404 "Not found" AFTER auth + gateway check.
# 503 here would mean the gateway is NOT configured.
say "5. Full chain: auth -> initialize"
EMAIL="paytest-$RANDOM$RANDOM@example.com"
PW="TestPass123!"
curl -s -X POST "$BASE/auth/register" -H "Content-Type: application/json" \
  -d "{\"full_name\":\"Pay Test\",\"email\":\"$EMAIL\",\"password\":\"$PW\"}" > /dev/null
TOKEN=$(curl -s -X POST "$BASE/auth/login" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PW\"}" | grep -oE '"access_token":"[^"]+"' | head -1 | sed 's/.*:"//;s/"//')
if [ -z "$TOKEN" ]; then
  fail "could not log in - auth problem"
else
  pass "registered + logged in (token received)"
  c=$(code -X POST "$BASE/payments/initialize" -H "Content-Type: application/json" \
      -H "Authorization: Bearer $TOKEN" -d '{"reference":"PAYTEST-NO-SUCH-BOOKING"}')
  if [ "$c" = "404" ]; then
    pass "initialize reached booking lookup - gateway + auth chain OK"
  elif [ "$c" = "503" ]; then
    fail "gateway not configured (503 from initialize)"
  else
    fail "unexpected initialize response: HTTP $c: $(body)"
  fi
fi

echo; echo "=================================="
if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED - integration is live."
  echo "Final proof (needs real GHc): make a booking and pay GHS 1 via Paystack."
else
  echo "$fails check(s) FAILED - see messages above."
fi
exit $fails
