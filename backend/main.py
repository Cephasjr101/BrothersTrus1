# Brother'sTrust Travel — full-stack travel booking platform.
# Flights, hotels, car rentals and visa appointments, one backend + one SPA.
import os
import time
from collections import defaultdict, deque
from pathlib import Path

import config  # noqa: F401  — loads .env BEFORE anything reads env vars

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import database
from database import get_db
from routers import admin, auth, bookings, cars, flights, hotels, payments, visa

FRONTEND_DIR = Path(os.getenv("BROTHERSTRUST_FRONTEND",
                              Path(__file__).resolve().parent.parent / "frontend"))

app = FastAPI(title="Brother'sTrust Travel API", version="2.0.0",
              description="Flights, hotels, car rentals and visa appointment booking")


@app.on_event("startup")
def startup():
    database.init_db()
    import sqlite3
    from routers.auth import ensure_admin
    conn = sqlite3.connect(database.DB_PATH)
    try:
        ensure_admin(conn)
        print(f"[bt-travel] admin account: {config.ADMIN_EMAIL}")
        if config.SECRET.startswith("dev-only"):
            print("[bt-travel] WARNING: using dev secret — set BROTHERSTRUST_SECRET in .env")
        if config.PAYSTACK_SECRET_KEY:
            print("[bt-travel] payments: LIVE Paystack mode")
        if config.SENDGRID_API_KEY:
            print("[bt-travel] email: SendGrid enabled")
        if config.AT_API_KEY:
            print("[bt-travel] sms: Africa's Talking enabled")
    finally:
        conn.close()


@app.get("/api/health")
def health():
    return {"ok": True, "service": "brotherstrust-travel", "version": "2.0.0"}


@app.post("/api/analytics")
async def track(request: Request, db=Depends(get_db)):
    """First-party, consent-gated analytics beacon from the SPA."""
    try:
        payload = await request.json()
    except Exception:
        return {"ok": True}
    kind = str(payload.get("kind", "page_view"))[:30]
    page = str(payload.get("page", "/"))[:200]
    db.execute("INSERT INTO analytics (kind, page) VALUES (?, ?)", (kind, page))
    return {"ok": True}


# ------------------------------------------------------------ middleware
@app.middleware("http")
async def force_https(request: Request, call_next):
    """Redirect HTTP -> HTTPS in production (skips localhost / test / ALLOW_HTTP)."""
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = (request.headers.get("x-forwarded-host") or request.url.hostname or "")
    local = host.split(":")[0] in ("localhost", "127.0.0.1", "testserver")
    if (proto == "http" and not local and not os.getenv("ALLOW_HTTP")):
        return RedirectResponse(str(request.url.replace(scheme="https")), status_code=308)
    return await call_next(request)


_buckets = defaultdict(deque)

@app.middleware("http")
async def rate_limit(request: Request, call_next):
    """Simple per-IP sliding-window limiter; stricter on /auth/* (brute-force/spam)."""
    if request.url.path.startswith("/assets/"):
        return await call_next(request)
    now = time.time()
    cls = "auth" if request.url.path.startswith("/auth/") else "global"
    limit = config.RATE_LIMIT_AUTH if cls == "auth" else config.RATE_LIMIT_GLOBAL
    key = (request.client.host if request.client else "anon", cls)
    q = _buckets[key]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= limit:
        return JSONResponse({"detail": "Too many requests — please slow down."}, status_code=429)
    q.append(now)
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data: https://*.googleusercontent.com; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline' https://www.gstatic.com; "
        "connect-src 'self' https://identitytoolkit.googleapis.com https://securetoken.googleapis.com "
        "https://www.googleapis.com; frame-src https://accounts.google.com; frame-ancestors 'none'")
    p = request.url.path
    if p.startswith(("/assets/", "/css/", "/js/")):
        resp.headers["Cache-Control"] = "public, max-age=86400"
    if request.headers.get("x-forwarded-proto") == "https":
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return resp


for r in (auth.router, flights.router, hotels.router, cars.router, visa.router,
          bookings.router, payments.router, admin.router):
    app.include_router(r)


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


@app.exception_handler(404)
async def not_found(request, exc):
    # SPA fallback: unknown GET paths render the app shell (which shows a custom 404)
    if request.method == "GET" and not request.url.path.startswith("/api"):
        index = FRONTEND_DIR / "index.html"
        if index.exists():
            return FileResponse(index)
    return JSONResponse({"detail": "Not found"}, status_code=404)
