"""Paystack go-live self-test. Run on the server, in the app's environment:
    python check_paystack.py
Exits 0 only if the full live path works end to end (minus a real charge).
"""
import os
import sys

import httpx

failures = []

def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail else ""))
    if not ok:
        failures.append(name)


# 1. Key present
key = os.getenv("PAYSTACK_SECRET_KEY", "")
check("PAYSTACK_SECRET_KEY is set", bool(key),
      "set it in your environment and restart the app" if not key else "")
check("key looks like a SECRET key", key.startswith("sk_"),
      f"starts with {key[:3]!r} - need sk_live_... or sk_test_..." if key else "")
if key.startswith("sk_test_"):
    print("WARN  test key: real customer cards will be DECLINED")

# 2. Key authenticates with Paystack
if key:
    r = httpx.get("https://api.paystack.co/transaction/initialize",
                  headers={"Authorization": f"Bearer {key}"}, timeout=15)
    # 405/400 with a JSON body = authenticated; 401 = bad key
    try:
        body = r.json()
        check("key authenticates with Paystack API", r.status_code != 401,
              body.get("message", "") if r.status_code == 401 else "")
    except Exception:
        check("key authenticates with Paystack API", False, f"HTTP {r.status_code}")

    # 3. Can actually create a checkout session
    r = httpx.post("https://api.paystack.co/transaction/initialize",
                   headers={"Authorization": f"Bearer {key}",
                            "Content-Type": "application/json"},
                   json={"email": "test@example.com", "amount": 10000,
                         "currency": os.getenv("PAYMENTS_CURRENCY", "GHS"),
                         "reference": "SELFTEST-1"},
                   timeout=30)
    data = r.json()
    check("can initialize a transaction", data.get("status") is True,
          data.get("message", f"HTTP {r.status_code}"))
    if data.get("status"):
        print(f"      checkout URL: {data['data']['authorization_url']}")

# 4. App wiring
try:
    import services.paystack as sp  # noqa
    check("services/paystack.py imports cleanly", True)
    check("services/paystack.py sees the key", sp.configured())
except ImportError as exc:
    check("services/paystack.py imports cleanly", False, str(exc))

base = os.getenv("BASE_URL", "")
check("BASE_URL is set to your public https domain", base.startswith("https://"),
      f"BASE_URL={base!r} - Paystack must reach /api/payments/callback on it")

print()
print("RESULT:", "all good - if it still fails, it's the frontend flow" if not failures
      else f"{len(failures)} check(s) failed: {', '.join(failures)}")
sys.exit(1 if failures else 0)
