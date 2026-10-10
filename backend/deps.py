"""Shared FastAPI dependencies + small helpers."""
import secrets
import sqlite3

from fastapi import Depends, HTTPException, Request

import security
from database import get_db


def current_user(request: Request, db: sqlite3.Connection = Depends(get_db)):
    """Resolve the Bearer token to a user row, or 401."""
    auth = request.headers.get("Authorization", "")
    payload = security.decode_token(auth[7:]) if auth.startswith("Bearer ") else None
    if not payload:
        raise HTTPException(401, "Sign in to continue")
    user = db.execute("SELECT * FROM users WHERE id = ?", (int(payload["sub"]),)).fetchone()
    if user is None:
        raise HTTPException(401, "Account no longer exists")
    return user


def admin_user(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin access required")
    return user


def make_reference(prefix: str = "BT") -> str:
    return f"{prefix}-{secrets.token_urlsafe(5).upper().replace('_', 'X').replace('-', 'K')}"


def notify(db: sqlite3.Connection, user_id: int, title: str, body: str = "") -> None:
    db.execute("INSERT INTO notifications (user_id, title, body) VALUES (?,?,?)",
               (user_id, title[:200], body[:500]))


def parse_date(value: str, field: str):
    from datetime import date
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        raise HTTPException(422, f"{field} must be a YYYY-MM-DD date")
