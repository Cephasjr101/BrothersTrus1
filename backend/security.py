"""Password hashing + JWT, stdlib only (no passlib / PyJWT dependencies).

Tokens are HS256 JWTs signed with BROTHERSTRUST_SECRET (set it in production!).
"""
import base64
import hashlib
import hmac
import json
import secrets
import time

import config

SECRET = config.SECRET
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, hexhash = stored.split("$", 1)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return hmac.compare_digest(dk.hex(), hexhash)


def create_token(user_id: int, role: str) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps({
        "sub": str(user_id), "role": role,
        "iat": int(time.time()), "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }).encode())
    sig = _b64url(hmac.new(SECRET.encode(), f"{header}.{payload}".encode(),
                           hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def decode_token(token: str) -> dict | None:
    try:
        header, payload, sig = token.split(".")
        expected = _b64url(hmac.new(SECRET.encode(), f"{header}.{payload}".encode(),
                                    hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(_b64url_decode(payload))
        if data.get("exp", 0) < time.time():
            return None
        return data
    except Exception:
        return None
