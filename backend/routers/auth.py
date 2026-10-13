"""Registration, login, profile."""
import hashlib
import json
import secrets as pysecrets
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

import config
import schemas
import security
from database import get_db
from deps import current_user
from services.notify import send_email
from services import firebase_auth as fb

router = APIRouter(prefix="/auth", tags=["auth"])

ADMIN_EMAIL = config.ADMIN_EMAIL
ADMIN_PASSWORD = config.ADMIN_PASSWORD


def ensure_admin(db: sqlite3.Connection) -> None:
    row = db.execute("SELECT id FROM users WHERE email = ?", (ADMIN_EMAIL,)).fetchone()
    if row is None:
        db.execute(
            "INSERT INTO users (email, password_hash, full_name, phone, role) VALUES (?,?,?,?,'admin')",
            (ADMIN_EMAIL, security.hash_password(ADMIN_PASSWORD), "Brother'sTrust Admin", ""))
        db.commit()


def _public_user(u: sqlite3.Row) -> dict:
    return {"id": u["id"], "email": u["email"], "full_name": u["full_name"],
            "phone": u["phone"], "role": u["role"], "created_at": u["created_at"],
            "firebase": bool(u["firebase_uid"])}


@router.post("/register")
def register(body: schemas.RegisterIn, db: sqlite3.Connection = Depends(get_db)):
    if body.website:  # honeypot: silently "succeed" for bots, create nothing
        return {"access_token": "", "token_type": "bearer", "user": None}
    email = body.email.lower().strip()
    exists = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if exists:
        raise HTTPException(409, "An account with this email already exists")
    cur = db.execute(
        "INSERT INTO users (email, password_hash, full_name, phone) VALUES (?,?,?,?)",
        (email, security.hash_password(body.password), body.full_name.strip(), body.phone.strip()))
    db.commit()
    user = db.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    return {"access_token": security.create_token(user["id"], user["role"]),
            "token_type": "bearer", "user": _public_user(user)}


@router.post("/login")
def login(body: schemas.LoginIn, db: sqlite3.Connection = Depends(get_db)):
    user = db.execute("SELECT * FROM users WHERE email = ?",
                      (body.email.lower().strip(),)).fetchone()
    if user is None or not security.verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Incorrect email or password")
    return {"access_token": security.create_token(user["id"], user["role"]),
            "token_type": "bearer", "user": _public_user(user)}


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.post("/forgot-password")
def forgot_password(body: schemas.ForgotPasswordIn, db: sqlite3.Connection = Depends(get_db)):
    """Always responds identically (no user enumeration). Sends email when SendGrid is
    configured; in demo mode returns the link directly so the flow is testable."""
    email = body.email.lower().strip()
    user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    dev_link = None
    if user:
        token = pysecrets.token_urlsafe(32)
        db.execute(
            "INSERT INTO password_resets (email, token_hash, expires_at) VALUES (?,?,datetime('now','+1 hour'))",
            (email, _hash_token(token)))
        dev_link = f"{config.BASE_URL}/#/reset?token={token}"
        send_email(email, "Reset your Brother'sTrust Travel password",
                   f"<p>Hi,</p><p>We received a request to reset your password. Click the link below "
                   f"(valid for 1 hour):</p><p><a href='{dev_link}'>Reset my password</a></p>"
                   f"<p>If you didn't request this, ignore this email — your password is unchanged.</p>")
    return {"ok": True,
            "detail": "If an account exists for this email, a reset link has been sent.",
            "dev_reset_link": dev_link if not config.SENDGRID_API_KEY else None}


@router.post("/reset-password")
def reset_password(body: schemas.ResetPasswordIn, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute(
        "SELECT * FROM password_resets WHERE token_hash=? AND used=0 AND expires_at > datetime('now')",
        (_hash_token(body.token),)).fetchone()
    if row is None:
        raise HTTPException(400, "This reset link is invalid or has expired — request a new one")
    db.execute("UPDATE users SET password_hash=? WHERE email=?",
               (security.hash_password(body.new_password), row["email"]))
    db.execute("UPDATE password_resets SET used=1 WHERE id=?", (row["id"],))
    db.execute("DELETE FROM password_resets WHERE email=? AND used=1", (row["email"],))
    return {"ok": True, "detail": "Password updated — you can sign in with your new password"}


@router.delete("/account")
def delete_account(body: schemas.DeleteAccountIn, db: sqlite3.Connection = Depends(get_db),
                   user=Depends(current_user)):
    """Close the account: cancels unpaid bookings (freeing visa slots), keeps confirmed
    history for records, then anonymises all personal data. Requires password."""
    if not security.verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Incorrect password")
    pending = db.execute("SELECT * FROM bookings WHERE user_id=? AND status='pending'",
                         (user["id"],)).fetchall()
    for b in pending:
        details = json.loads(b["details"])
        if b["type"] == "visa" and details.get("center") and details.get("date"):
            db.execute(
                "UPDATE visa_slots SET booked=MAX(booked-?,0) WHERE country=? AND center=? AND date=? AND time=?",
                (len(json.loads(b["travelers"])), details.get("country_code", ""),
                 details["center"], details["date"], details.get("time", "")))
    db.execute("UPDATE bookings SET status='cancelled', refund_amount=0, updated_at=datetime('now') "
               "WHERE user_id=? AND status='pending'", (user["id"],))
    db.execute("UPDATE payments SET status='failed' WHERE booking_id IN "
               "(SELECT id FROM bookings WHERE user_id=?) AND status='pending'", (user["id"],))
    db.execute("DELETE FROM notifications WHERE user_id=?", (user["id"],))
    db.execute("DELETE FROM password_resets WHERE email=?", (user["email"],))
    db.execute(
        "UPDATE users SET email=?, full_name='Deleted account', phone='', password_hash='!' WHERE id=?",
        (f"deleted_{user['id']}@removed.bt-travel", user["id"]))
    return {"ok": True, "detail": "Your account has been closed and your data anonymised"}


@router.get("/firebase-config")
def firebase_config():
    """Public Firebase client config (the API key is not a secret by design)."""
    if not config.FIREBASE_API_KEY:
        raise HTTPException(404, "Firebase sign-in is not configured on this server")
    return {"apiKey": config.FIREBASE_API_KEY, "authDomain": config.FIREBASE_AUTH_DOMAIN,
            "projectId": config.FIREBASE_PROJECT_ID, "appId": config.FIREBASE_APP_ID}


@router.post("/firebase")
def firebase_signin(body: schemas.FirebaseSignIn, db: sqlite3.Connection = Depends(get_db)):
    """Verify a Firebase ID token (Google sign-in), then link-or-create a local
    account and issue our own session JWT so the rest of the app is unchanged."""
    claims = fb.verify_id_token(body.id_token)
    if not claims:
        raise HTTPException(401, "Invalid or expired Firebase sign-in — try again")
    uid, email = claims["sub"], (claims.get("email") or "").lower().strip()
    name = (claims.get("name") or (email.split("@")[0] if email else "Traveller")).strip()[:120]
    user = db.execute("SELECT * FROM users WHERE firebase_uid = ?", (uid,)).fetchone()
    if user is None and email:
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user is not None:
            db.execute("UPDATE users SET firebase_uid = ? WHERE id = ?", (uid, user["id"]))
            db.commit()
    if user is None:
        if not email:
            raise HTTPException(400, "This Google account has no email address")
        db.execute(
            "INSERT INTO users (email, password_hash, full_name, role, firebase_uid) VALUES (?, '!firebase', ?, 'user', ?)",
            (email, name, uid))
        db.commit()
        user = db.execute("SELECT * FROM users WHERE firebase_uid = ?", (uid,)).fetchone()
    return {"access_token": security.create_token(user["id"], user["role"]),
            "token_type": "bearer", "user": _public_user(user)}


@router.get("/me")
def me(user=Depends(current_user)):
    return _public_user(user)
