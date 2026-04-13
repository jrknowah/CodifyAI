from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import settings
import hashlib

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

# ── In-memory token blacklist (use Redis in production) ──────────────────────
_blacklisted_tokens: set[str] = set()


def _token_fingerprint(token: str) -> str:
    """Store a hash of the token, not the token itself."""
    return hashlib.sha256(token.encode()).hexdigest()


def blacklist_token(token: str) -> None:
    _blacklisted_tokens.add(_token_fingerprint(token))


def is_token_blacklisted(token: str) -> bool:
    return _token_fingerprint(token) in _blacklisted_tokens


# ── Password ─────────────────────────────────────────────────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


# ── JWT ──────────────────────────────────────────────────────────────────────

def create_access_token(subject: str, extra: dict = {}) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {"sub": subject, "exp": expire, "type": "access", **extra}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days
    )
    payload = {"sub": subject, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.refresh_secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict:
    """Decode and validate an access token. Raises JWTError on failure."""
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    if payload.get("type") != "access":
        raise JWTError("Invalid token type")
    if is_token_blacklisted(token):
        raise JWTError("Token has been revoked")
    return payload


def decode_refresh_token(token: str) -> dict:
    """Decode and validate a refresh token. Raises JWTError on failure."""
    payload = jwt.decode(token, settings.refresh_secret_key, algorithms=[settings.algorithm])
    if payload.get("type") != "refresh":
        raise JWTError("Invalid token type")
    return payload
