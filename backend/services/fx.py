# Currency conversion for live providers (Duffel/LiteAPI bill in USD; the site
# sells in GHS). Rate source, in priority order:
#   1. USD_GHS_RATE env var  -> set this to Absa Ghana's daily rate for full control
#   2. Auto-fetch from a free public API (open.er-api.com), cached 1 hour
#   3. Last-resort fallback constant
# On top of the rate, FX_FEE_PER_USD (default 1) is added per $1 as your bank/
# conversion recovery fee — so $1 converts at (rate + 2) cedis.
import json
import os
import time
import urllib.request

_cache = {"rate": None, "at": 0.0}
FALLBACK_RATE = 15.5


def _rate() -> float:
    manual = (os.getenv("USD_GHS_RATE") or "").strip()
    if manual:
        return float(manual)
    if _cache["rate"] and time.time() - _cache["at"] < 3600:
        return _cache["rate"]
    try:
        with urllib.request.urlopen("https://open.er-api.com/v6/latest/USD", timeout=15) as r:
            data = json.loads(r.read().decode())
        _cache.update(rate=float(data["rates"]["GHS"]), at=time.time())
        return _cache["rate"]
    except Exception:
        return _cache["rate"] or FALLBACK_RATE


def fee_per_usd() -> float:
    return float(os.getenv("FX_FEE_PER_USD", "1") or 0)


def current_rate_display() -> dict:
    return {"rate": round(_rate(), 2), "fee_per_usd": fee_per_usd(),
            "effective": round(_rate() + fee_per_usd(), 2)}


def to_ghs(amount: float, currency: str = "USD") -> float:
    """Convert a provider amount into GHS including the per-dollar bank fee."""
    if not amount or (currency or "").upper() in ("GHS", ""):
        return amount
    return amount * (_rate() + fee_per_usd())   # USD (or foreign) -> GHS at Absa rate + GH¢1/$
