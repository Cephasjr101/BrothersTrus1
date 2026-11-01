"""Currency conversion for display. Rates are live (open.er-api.com, USD-based,
refreshed hourly) and fall back to a sane static table offline.

Canonical money inside the app is ALWAYS GHS - bookings and Paystack charges
stay in cedis. Other currencies are DISPLAY-ONLY formatting for visitors.
"""
import os
import threading
import time
from datetime import date, datetime

import httpx

FX_FEE_PER_USD = float(os.getenv("FX_FEE_PER_USD", "1") or 1)   # GHc per $1 recovery fee
BASE = "GHS"

# Optional manual USD->GHS rate: set USD_GHS_RATE (e.g. "15.80") in fly secrets
# to pin the cedi rate instead of using the live API rate.
_ENV_GHS_RATE = float(os.getenv("USD_GHS_RATE", "0") or 0)

# Flat per-booking service fee in USD (flights only): set SERVICE_FEE_USD in secrets.
SERVICE_FEE_USD = float(os.getenv("SERVICE_FEE_USD", "0") or 0)

_lock = threading.Lock()
_rates: dict = {}
_fetched_at = 0.0

_STATIC = {"USD": 1.0, "GHS": 15.5, "NGN": 1550.0, "GBP": 0.79, "EUR": 0.92,
           "KES": 129.0, "ETB": 118.0, "AED": 3.67, "ZAR": 17.5, "EGP": 48.0,
           "CAD": 1.38, "AUD": 1.52, "INR": 84.0, "CNY": 7.1, "RWF": 1350.0,
           "XOF": 605.0, "XAF": 605.0, "SLL": 0.0, "LRD": 0.0}

# country code -> national currency ("signature currency" per nation)
COUNTRY_CURRENCY = {
    "GH": "GHS", "NG": "NGN", "US": "USD", "GB": "GBP", "KE": "KES",
    "ET": "ETB", "AE": "AED", "ZA": "ZAR", "FR": "EUR", "DE": "EUR",
    "NL": "EUR", "IT": "EUR", "ES": "EUR", "PT": "EUR", "IE": "EUR",
    "BE": "EUR", "AT": "EUR", "GR": "EUR", "EG": "EGP", "CA": "CAD",
    "AU": "AUD", "IN": "INR", "CN": "CNY", "RW": "RWF", "CI": "XOF",
    "SN": "XOF", "CM": "XAF", "LR": "LRD",
}

# IANA timezone -> country (for automatic currency detection on the frontend)
TZ_COUNTRY = {
    "Africa/Accra": "GH", "Africa/Lagos": "NG", "Africa/Abidjan": "CI",
    "Europe/London": "GB", "Europe/Paris": "FR", "Europe/Berlin": "DE",
    "Europe/Amsterdam": "NL", "Europe/Madrid": "ES", "Europe/Rome": "IT",
    "America/New_York": "US", "America/Chicago": "US", "America/Denver": "US",
    "America/Los_Angeles": "US", "America/Toronto": "CA",
    "Africa/Nairobi": "KE", "Africa/Addis_Ababa": "ET", "Africa/Johannesburg": "ZA",
    "Asia/Dubai": "AE", "Africa/Cairo": "EG", "Africa/Kigali": "RW",
    "Australia/Sydney": "AU", "Asia/Kolkata": "IN", "Asia/Shanghai": "CN",
    "Africa/Dakar": "SN", "Africa/Douala": "CM", "Africa/Monrovia": "LR",
}


def _refresh():
    global _rates, _fetched_at
    if time.time() - _fetched_at < 3600:
        return
    try:
        r = httpx.get("https://open.er-api.com/v6/latest/USD", timeout=12)
        data = r.json()
        if data.get("result") == "success":
            with _lock:
                _rates = dict(data.get("rates") or {})
                _fetched_at = time.time()
    except Exception:
        pass


def _rates_now() -> dict:
    if not _rates:
        _refresh()
    return _rates or {}


def usd_rate(ccy: str) -> float | None:
    if ccy == "GHS" and _ENV_GHS_RATE:
        return _ENV_GHS_RATE
    r = _rates_now()
    v = r.get(ccy) or _STATIC.get(ccy)
    return float(v) if v else None


def ghs_per_usd() -> float:
    """GHS per USD. When USD_GHS_RATE is pinned in env it is used PURELY
    (no fee on top); live rates add the per-dollar recovery fee."""
    if _ENV_GHS_RATE:
        return _ENV_GHS_RATE
    base = usd_rate("GHS") or _STATIC["GHS"]
    return base + FX_FEE_PER_USD


def to_ghs(amount: float, ccy: str = "USD") -> float:
    """Convert any supported currency to GHS (canonical)."""
    if not amount:
        return 0.0
    if (ccy or "USD").upper() == "GHS":
        return round(float(amount), 2)
    u = usd_rate(ccy.upper())
    if not u:
        return round(float(amount), 2)
    return round(float(amount) / u * ghs_per_usd(), 2)


def convert(ghs_amount: float, to_ccy: str) -> tuple[float, str]:
    """Convert a GHS amount to a display currency. Returns (amount, ccy).
    Unknown currencies return the GHS amount unchanged."""
    to = (to_ccy or "GHS").upper()
    if to == "GHS" or not ghs_amount:
        return round(float(ghs_amount or 0), 2), "GHS"
    base = usd_rate("GHS")
    target = usd_rate(to)
    if not base or not target:
        return round(float(ghs_amount), 2), "GHS"
    usd = float(ghs_amount) / (base + FX_FEE_PER_USD)
    return round(usd * target, 2), to


def currency_for_country(country_code: str | None) -> str:
    return COUNTRY_CURRENCY.get((country_code or "").upper(), "GHS")


def rates_payload() -> dict:
    """Public payload for the frontend currency display layer."""
    r = _rates_now()
    rates = {k: r.get(k, v) for k, v in _STATIC.items()}
    return {"base": "USD", "ghsPerUsd": round(ghs_per_usd(), 4),
            "serviceFeeUsd": SERVICE_FEE_USD,
            "rates": rates, "feePerUsd": FX_FEE_PER_USD,
            "countryCurrencies": COUNTRY_CURRENCY, "tzCountry": TZ_COUNTRY,
            "canonical": BASE}


def describe() -> str:
    return f"USD 1 ~ GHS {ghs_per_usd():.2f}"


def current_rate_display() -> str:
    """Human-readable rate string for /meta/flights."""
    base = usd_rate("GHS") or _STATIC["GHS"]
    return f"USD 1 \u2248 GH\u00a2 {base + FX_FEE_PER_USD:.2f}"
