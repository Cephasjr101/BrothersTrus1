"""Paystack live gateway - the ONLY payment backend.

Env:
  PAYSTACK_SECRET_KEY  secret key from https://dashboard.paystack.com (required)
  PAYMENTS_CURRENCY    default "GHS"

Interface used by routers/payments.py:
  configured()                              -> bool
  initialize(email, amount_major, ref, cb)  -> hosted checkout URL
  verify(reference)                         -> (ok, data); data["amount"] in PESWAS
  valid_signature(raw_body, signature)      -> bool (HMAC-SHA512)

Amount convention: initialize() takes MAJOR units (GHS) because bookings store
GHc amounts; verify() returns data["amount"] in MINOR units (pesewas) so the
router can compare against amount * 100 uniformly.
"""
import hashlib
import hmac
import os

import httpx

BASE = "https://api.paystack.co"
SECRET = os.getenv("PAYSTACK_SECRET_KEY", "")
CURRENCY = os.getenv("PAYMENTS_CURRENCY", "GHS")


class PaystackError(RuntimeError):
    pass


def configured() -> bool:
    return bool(SECRET)


def _headers() -> dict:
    return {"Authorization": f"Bearer {SECRET}", "Content-Type": "application/json"}


def initialize(email: str, amount_major: float, reference: str, callback_url: str,
               booking_reference: str = "") -> str:
    """Create a hosted checkout session and return the authorization URL."""
    payload = {
        "email": email,
        "amount": int(round(amount_major * 100)),   # Paystack charges in pesewas
        "currency": CURRENCY,
        "reference": reference,
        "callback_url": callback_url,
        "metadata": {"booking_reference": booking_reference},
    }
    r = httpx.post(f"{BASE}/transaction/initialize", headers=_headers(),
                   json=payload, timeout=30)
    data = r.json()
    if r.status_code >= 400 or not data.get("status"):
        raise PaystackError(f"initialize failed: {data.get('message') or r.text[:200]}")
    return data["data"]["authorization_url"]


def verify(reference: str):
    """Confirm a transaction server-side. Returns (ok, data) with
    data["amount"] normalized to pesewas so callers compare amount * 100."""
    r = httpx.get(f"{BASE}/transaction/verify/{reference}",
                  headers=_headers(), timeout=30)
    data = r.json()
    d = data.get("data") or {}
    ok = r.status_code == 200 and data.get("status") is True \
        and d.get("status") == "success"
    return ok, d   # d["amount"] is already in pesewas from Paystack


def valid_signature(raw_body: bytes, signature: str) -> bool:
    """Paystack signs webhooks with HMAC-SHA512 of the raw body using the
    secret key. Always compare with the raw request bytes, never a re-serialized dict."""
    if not SECRET or not signature:
        return False
    digest = hmac.new(SECRET.encode(), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(signature, digest)
