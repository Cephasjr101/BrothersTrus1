# Central configuration. Loads .env (simple KEY=VALUE) without extra deps.
# NEVER put secrets in frontend files -- only this file + environment variables.
import os
from pathlib import Path

def load_env(path):
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

load_env(Path(__file__).resolve().parent.parent / ".env")

# --- core ---
SECRET = os.getenv("BROTHERSTRUST_SECRET", "dev-only-secret-change-me")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@brotherstrusttravel.com").lower()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "BT#Admin1")

# --- payments (live mode activates when the key is present) ---
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "")

# --- firebase authentication (frontend Google sign-in; backend verifies ID tokens) ---
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "")
FIREBASE_AUTH_DOMAIN = os.getenv("FIREBASE_AUTH_DOMAIN", "")
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "")
FIREBASE_APP_ID = os.getenv("FIREBASE_APP_ID", "")

# --- notifications (each channel activates when its key is present) ---
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL", "no-reply@brotherstrusttravel.com")
SENDGRID_FROM_NAME = os.getenv("SENDGRID_FROM_NAME", "Brother'sTrust Travel")
AT_USERNAME = os.getenv("AT_USERNAME", "sandbox")          # Africa's Talking
AT_API_KEY = os.getenv("AT_API_KEY", "")
AT_SENDER_ID = os.getenv("AT_SENDER_ID", "BT-TRAVEL")

# --- abuse protection ---
RATE_LIMIT_AUTH = int(os.getenv("RATE_LIMIT_AUTH", "10"))      # requests / minute / IP
RATE_LIMIT_GLOBAL = int(os.getenv("RATE_LIMIT_GLOBAL", "240"))
