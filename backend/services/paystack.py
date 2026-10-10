# Live Paystack integration (stdlib urllib -- no SDK dependency).
# Silent no-op/fallback when PAYSTACK_SECRET_KEY is not configured.
import hashlib
import hmac
import json
import urllib.parse
import urllib.request

import config

BASE = "https://api.paystack.co"


def configured() -> bool:
    return bool(config.PAYSTACK_SECRET_KEY)


def _post(path, payload):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": f"Bearer {config.PAYSTACK_SECRET_KEY}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())


def _get(path):
    req = urllib.request.Request(
        BASE + path,
        headers={"Authorization": f"Bearer {config.PAYSTACK_SECRET_KEY}"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())


def initialize(email: str, amount_ngn: float, gateway_ref: str,
               callback_url: str, booking_reference: str) -> str:
    """Create a Paystack transaction, returning the hosted checkout URL."""
    data = _post("/transaction/initialize", {
        "email": email, "amount": int(round(amount_ngn * 100)),  # kobo
        "reference": gateway_ref, "callback_url": callback_url,
        "metadata": {"booking_reference": booking_reference, "source": "bt-travel"},
    })
    if not data.get("status"):
        raise RuntimeError(data.get("message", "Paystack rejected the transaction"))
    return data["data"]["authorization_url"]


def verify(gateway_ref: str):
    """Server-side confirmation. Returns (success, paystack_data)."""
    data = _get("/transaction/verify/" + urllib.parse.quote(gateway_ref, safe=""))
    d = data.get("data") or {}
    return bool(data.get("status")) and d.get("status") == "success", d


def valid_signature(raw_body: bytes, signature: str) -> bool:
    digest = hmac.new(config.PAYSTACK_SECRET_KEY.encode(), raw_body,
                      hashlib.sha512).hexdigest()
    return hmac.compare_digest(digest, signature or "")
