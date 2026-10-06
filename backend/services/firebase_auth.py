# Firebase ID-token verification (RS256 against Google's public JWKS).
# Requires FIREBASE_PROJECT_ID; needs network access to fetch signing keys.
import config

try:
    import jwt as pyjwt
    from jwt import PyJWKClient
except Exception:  # PyJWT[crypto] not installed -> Firebase sign-in unavailable
    pyjwt = None

_jwks = None


def available() -> bool:
    return bool(config.FIREBASE_PROJECT_ID) and pyjwt is not None


def verify_id_token(id_token: str):
    """Return decoded Firebase claims, or None if invalid/unverifiable."""
    if not available() or not id_token:
        return None
    global _jwks
    try:
        if _jwks is None:
            _jwks = PyJWKClient(
                "https://www.googleapis.com/robot/v1/metadata/jwk/securetoken@system.gserviceaccount.com")
        key = _jwks.get_signing_key_from_jwt(id_token)
        claims = pyjwt.decode(
            id_token, key.key, algorithms=["RS256"],
            audience=config.FIREBASE_PROJECT_ID,
            issuer=f"https://securetoken.google.com/{config.FIREBASE_PROJECT_ID}")
        if not claims.get("email_verified", True):
            return None
        return claims
    except Exception:
        return None
