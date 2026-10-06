"""SQLite storage layer for Brother'sTrust Travel.

Stdlib sqlite3 only -- no ORM needed. One connection per request, WAL mode,
and a tiny migration hook (PRAGMA user_version) so the schema can grow.
"""
import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("BROTHERSTRUST_DB", str(BASE_DIR / "bt-travel.db")))

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name     TEXT NOT NULL DEFAULT '',
    phone         TEXT NOT NULL DEFAULT '',
    firebase_uid  TEXT,
    role          TEXT NOT NULL DEFAULT 'user',          -- user | admin
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS bookings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    reference   TEXT UNIQUE NOT NULL,                    -- e.g. DOM-8K2XQ4
    user_id     INTEGER NOT NULL REFERENCES users(id),
    type        TEXT NOT NULL,                           -- flight | hotel | car | visa
    status      TEXT NOT NULL DEFAULT 'pending',         -- pending | confirmed | cancelled | completed
    amount      REAL NOT NULL,
    currency    TEXT NOT NULL DEFAULT 'NGN',
    details     TEXT NOT NULL DEFAULT '{}',              -- JSON snapshot of the booked product
    travelers   TEXT NOT NULL DEFAULT '[]',              -- JSON array of traveler/applicant names
    refund_amount REAL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id);
CREATE INDEX IF NOT EXISTS idx_bookings_ref  ON bookings(reference);

CREATE TABLE IF NOT EXISTS payments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    reference    TEXT UNIQUE NOT NULL,                   -- gateway reference (pay-...)
    booking_id   INTEGER NOT NULL REFERENCES bookings(id),
    amount       REAL NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',        -- pending | paid | failed | refunded
    method       TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    paid_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_payments_booking ON payments(booking_id);

CREATE TABLE IF NOT EXISTS visa_slots (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    country  TEXT NOT NULL,
    center   TEXT NOT NULL,
    date     TEXT NOT NULL,
    time     TEXT NOT NULL,
    capacity INTEGER NOT NULL DEFAULT 4,
    booked   INTEGER NOT NULL DEFAULT 0,
    UNIQUE(country, center, date, time)
);

CREATE TABLE IF NOT EXISTS password_resets (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    email      TEXT NOT NULL,
    token_hash TEXT UNIQUE NOT NULL,
    expires_at TEXT NOT NULL,
    used       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS analytics (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT NOT NULL DEFAULT 'page_view',
    page       TEXT NOT NULL DEFAULT '/',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_analytics_kind ON analytics(kind);

CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    title      TEXT NOT NULL,
    body       TEXT NOT NULL DEFAULT '',
    read_at    TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def get_db():
    """FastAPI dependency: one connection per request, auto-commit."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    if "firebase_uid" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN firebase_uid TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_firebase_uid ON users(firebase_uid)")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
    conn.close()
