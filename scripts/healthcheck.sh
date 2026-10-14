#!/usr/bin/env bash
# Brother'sTrust Travel - full configuration health check
# Run inside the Render Shell (or any machine with the env vars set)
echo "===== Brother'sTrust full config check ====="
echo
echo "--- Environment variables ---"
check_var() { if [ -n "${!1}" ]; then echo "[OK] $1 is set"; else echo "[!!] $1 is MISSING"; fi }
check_var BROTHERSTRUST_SECRET
check_var ADMIN_PASSWORD
check_var PAYSTACK_SECRET_KEY
check_var DUFFEL_API_TOKEN
check_var LITEAPI_KEY
check_var USD_GHS_RATE
check_var MARKUP_PERCENT
check_var SENDGRID_API_KEY
check_var AT_API_KEY
check_var FIREBASE_API_KEY
check_var FIREBASE_PROJECT_ID
check_var FIREBASE_APP_ID
echo
echo "--- Key types ---"
case "$PAYSTACK_SECRET_KEY" in
  sk_live*) echo "[OK] Paystack LIVE key";;
  sk_test*) echo "[~~] Paystack TEST key (no real money)";;
  *) echo "[!!] Paystack key has invalid prefix";;
esac
case "$DUFFEL_API_TOKEN" in
  duffel_live*) echo "[OK] Duffel LIVE token";;
  duffel_test*) echo "[~~] Duffel TEST token (sandbox)";;
  *) echo "[!!] Duffel token has invalid prefix";;
esac
case "$LITEAPI_KEY" in
  prod_*) echo "[~~] LiteAPI PRODUCTION key (real money!)";;
  *test*|*sandbox*) echo "[OK] LiteAPI sandbox/test key";;
  *) echo "[??] LiteAPI key prefix unknown: ${LITEAPI_KEY:0:12}...";;
esac
if [ "$BROTHERSTRUST_SECRET" = "dev-only-secret-change-me" ] || [ -z "$BROTHERSTRUST_SECRET" ]; then
  echo "[!!] DEV/default secret in use - set BROTHERSTRUST_SECRET"
else
  echo "[OK] Custom BROTHERSTRUST_SECRET in use"
fi
echo
echo "--- Live API connectivity ---"
python - <<'EOF'
import os, json, urllib.request

def get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status, r.read().decode()

def check(name, url, headers, hint=""):
    try:
        s, body = get(url, headers)
        print(f"[OK] {name} -> HTTP {s} {hint}")
        return body
    except urllib.error.HTTPError as e:
        print(f"[!!] {name} -> HTTP {e.code}: {e.read().decode()[:120]}")
    except Exception as e:
        print(f"[!!] {name} -> {e}")
    return None

check("Your app /api/health", "http://localhost:8000/api/health", {})

if os.getenv("PAYSTACK_SECRET_KEY"):
    check("Paystack (account balance)", "https://api.paystack.co/balance",
          {"Authorization": "Bearer " + os.environ["PAYSTACK_SECRET_KEY"]})

if os.getenv("DUFFEL_API_TOKEN"):
    check("Duffel (airline list)", "https://api.duffel.com/air/airlines",
          {"Authorization": "Bearer " + os.environ["DUFFEL_API_TOKEN"], "Duffel-Version": "v2"})

if os.getenv("LITEAPI_KEY"):
    check("LiteAPI (Ghana hotels)", "https://api.liteapi.travel/v3.0/data/hotels?countryCode=GH&limit=1",
          {"X-API-Key": os.environ["LITEAPI_KEY"]})

body = check("Your app /meta/flights", "http://localhost:8000/meta/flights", {})
if body:
    d = json.loads(body)
    print("     -> flight provider:", d.get("provider"), "| FX:", d.get("fx"))

body = check("Your app /auth/firebase-config", "http://localhost:8000/auth/firebase-config", {})
if body:
    print("     -> firebase projectId:", json.loads(body).get("projectId"))

try:
    import jwt
    print("[OK] PyJWT installed:", jwt.__version__)
except ImportError:
    print("[!!] PyJWT NOT installed - redeploy with 'Clear build cache'")
EOF
echo
echo "===== check complete ====="
