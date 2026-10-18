#!/usr/bin/env bash
# Google Login / Firebase - full diagnostic

echo "======== GOOGLE LOGIN DIAGNOSTIC ========"

echo
echo "-- 1. Environment variables --"
for v in FIREBASE_API_KEY FIREBASE_AUTH_DOMAIN FIREBASE_PROJECT_ID FIREBASE_APP_ID; do
  if [ -n "${!v}" ]; then echo "  [OK] $v is set"; else echo "  [!!] $v MISSING"; fi
done
echo
echo "-- 2. Project ID matches auth domain? --"
echo "  project_id : ${FIREBASE_PROJECT_ID}"
echo "  auth_domain: ${FIREBASE_AUTH_DOMAIN}"

echo
echo "-- 3. Backend pieces --"
echo -n "  verify service: "; grep -c "verify_id_token" /app/backend/services/firebase_auth.py
echo -n "  endpoints:      "; grep -c "firebase" /app/backend/routers/auth.py
python - <<'EOF'
try:
    import jwt
    print(f"  [OK] PyJWT {jwt.__version__} installed")
except ImportError:
    print("  [!!] PyJWT NOT installed - Clear build cache & deploy")
import sys
sys.path.insert(0, "/app/backend")
try:
    from services import firebase_auth as fb
    print(f"  [OK] verifier available: {fb.available()}  (needs project_id + PyJWT)")
except Exception as e:
    print(f"  [!!] verifier import failed: {e}")
EOF

echo
echo "-- 4. Config endpoint (local + public domain) --"
python - <<'EOF'
import urllib.request, json
for name, url in [("localhost", "http://localhost:8000/auth/firebase-config"),
                  ("japafly.com", "https://www.japafly.com/auth/firebase-config")]:
    try:
        body = urllib.request.urlopen(url, timeout=15).read().decode()
        if body.strip().startswith("{"):
            d = json.loads(body)
            print(f"  [OK] {name}: JSON served, projectId={d.get('projectId')}, apiKey={'set' if d.get('apiKey') else 'EMPTY'}")
        else:
            print(f"  [!!] {name}: returned HTML (route missing -> stale backend)")
    except Exception as e:
        print(f"  [!!] {name}: {type(e).__name__} {e}")
EOF

echo
echo "-- 5. Login backend (email/password flow) --"
python - <<'EOF'
import json, time, urllib.request
B = "http://localhost:8000"
def call(m, p, h=None, d=None):
    r = urllib.request.Request(B + p, method=m, data=json.dumps(d).encode() if d else None,
        headers={"Content-Type": "application/json", **(h or {})})
    with urllib.request.urlopen(r, timeout=20) as x:
        return json.loads(x.read().decode() or "{}")
try:
    e = f"g{int(time.time())}@t.bt"
    reg = call("POST", "/auth/register", d={"email": e, "password": "secret1", "full_name": "G Check", "phone": "0551234567"})
    tok = reg["access_token"]
    me = call("GET", "/auth/me", h={"Authorization": "Bearer " + tok})
    print(f"  [OK] register+token+me works ({me['email']}) - auth backend healthy")
except Exception as ex:
    print(f"  [!!] auth backend failed: {ex}")
EOF

echo
echo "-- 6. /auth/firebase endpoint behavior --"
python - <<'EOF'
import json, urllib.request, urllib.error
req = urllib.request.Request("http://localhost:8000/auth/firebase",
    data=json.dumps({"id_token": "x" * 60}).encode(),
    headers={"Content-Type": "application/json"}, method="POST")
try:
    urllib.request.urlopen(req, timeout=20)
    print("  [??] garbage token was ACCEPTED (should not happen)")
except urllib.error.HTTPError as e:
    code = e.code
    body = e.read().decode()[:130]
    if code == 401:
        print(f"  [OK] garbage token rejected with 401 - endpoint + verifier RUNNING ({body})")
    elif code == 500:
        print(f"  [!!] 500 - verifier unavailable: {body}")
    else:
        print(f"  [??] HTTP {code}: {body}")
EOF

echo
echo "-- 7. CSP allows Firebase? --"
python - <<'EOF'
import urllib.request
h = urllib.request.urlopen("http://localhost:8000/api/health", timeout=10).headers
csp = h.get("Content-Security-Policy", "")
checks = {"gstatic (SDK)": "gstatic.com" in csp,
          "identitytoolkit (auth)": "identitytoolkit" in csp,
          "accounts.google (popup)": "accounts.google.com" in csp}
for k, v in checks.items():
    print(f"  [{'OK' if v else '!!'}] CSP: {k}")
EOF

echo
echo "-- 8. Frontend wiring --"
echo -n "  signInWithGoogle code: "; grep -c "signInWithGoogle" /app/frontend/js/app.js
echo -n "  config fetch:          "; grep -c "firebase-config" /app/frontend/js/app.js

echo
echo "======== INTERPRETATION ========"
echo "If sections 1-6 are OK but the Google popup still fails with"
echo "auth/internal-error, the problem is INSIDE your Firebase project:"
echo "  - Firebase Console -> Authentication -> Sign-in method -> Google -> ENABLE"
echo "  - Authentication -> Settings -> Authorized domains -> add www.japafly.com"
echo "  - console.cloud.google.com -> your API key -> set restrictions to NONE (test)"
echo "  - Then retry. Browser F12 console shows the exact code."
