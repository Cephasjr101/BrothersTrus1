# Brother'sTrust Travel — Flights, Hotels, Cars & Visa Booking

A full-stack travel booking platform in the style of Wakanow: one FastAPI
backend (SQLite, zero external services needed) + one self-contained SPA.

## Features

| Module | What it does |
|---|---|
| ✈️ Flights | Search 12 airports / 14 routes, 4 cabin classes, deterministic daily schedules, fare engine (demand + advance-purchase pricing), multi-passenger pricing, one-way & round-trip |
| 🏨 Hotels | 26 hotels in 10 cities, room-type availability computed live from bookings, VAT, sold-out handling |
| 🚗 Cars | 6 vehicle classes in 7 cities, fleet availability per date range, supplier assignment |
| 🛂 Visa | 12 destination countries with requirement profiles (visa-free / eVisa / VFS / embassy), capacity-managed appointment slots, document checklists, consultant hand-off |
| 💳 Payments | Mock gateway shaped exactly like Paystack (`initialize` → checkout page → `confirm`, plus `callback` + `webhook`). Swap in real Paystack/Flutterwave by replacing `routers/payments.py` internals |
| 👤 Accounts | Register/login (PBKDF2 + HS256 JWT, stdlib only), booking history, cancellations with refund rules, in-app notifications |
| 🛠 Admin | Stats dashboard (revenue, bookings by type/status, daily series), all bookings, all users |

## Quick start

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Open http://localhost:8000 — the SPA is served by the same process.
API docs at http://localhost:8000/docs.

### Demo accounts

- Admin: `admin@brotherstrusttravel.com` / `BT#Admin1` (change via `ADMIN_EMAIL` / `ADMIN_PASSWORD` env vars)
- Regular users: register from the UI (top-right "Sign in" → "Create account")

### Docker

```bash
docker build -t bt-travel .
docker run -p 8000:8000 bt-travel
```

## Layout

```
backend/
  main.py          # app entrypoint, static mount, SPA fallback
  database.py      # sqlite schema + connection dependency
  security.py      # PBKDF2 passwords + stdlib JWT
  seed.py          # flight/hotel/car/visa catalog + pricing engine
  deps.py          # auth deps, helpers
  schemas.py       # pydantic request models
  routers/         # auth, flights, hotels, cars, visa, bookings, payments, admin
frontend/
  index.html       # app shell
  css/style.css    # design system (CSS variables — rebrand by editing :root)
  js/app.js        # hash-routed SPA (no build step, no frameworks)
```

## Design notes

- **No build step, no JS frameworks** — the frontend is a single dependency-free
  SPA, so it deploys identically on Netlify/Vercel (static) or behind uvicorn.
- **Deterministic flight schedules** — flights are generated from route+date, so
  search results are re-validated and re-priced server-side at booking time;
  a fare can't be tampered with from the client.
- **Availability is computed, not stored** — hotel rooms and car fleets derive
  availability from the bookings table; visa slots are capacity-managed rows.
- **Idempotent payments** — confirming twice settles once; cancelling refunds
  per product rules (flights 80%, hotels 90%, cars 85%, visa 90%).
- Booking references look like `BTFL-…`, `BTHT-…`, `BTCR-…`, `BTVS-…`.

## Going live

1. Set `BROTHERSTRUST_SECRET` (long random string).
2. Change `ADMIN_PASSWORD`.
3. Replace the mock gateway in `routers/payments.py` with Paystack/Flutterwave
   calls — the endpoint shapes are already compatible.
4. Put uvicorn behind nginx/Caddy and serve the SPA from the same host.
5. Back up `bt-travel.db` (or move to Postgres by swapping `database.py`).

## License

MIT — built for Brother'sTrust Travel.
