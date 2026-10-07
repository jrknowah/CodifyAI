import time
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import pyotp
from cryptography.fernet import Fernet
from jwt import InvalidTokenError as JWTError  # noqa: F401 — re-exported for callers

from app.core.config import settings

BCRYPT_ROUNDS = 12
TOTP_INTERVAL = 30

_fernet = Fernet(settings.encryption_key.encode())


# ── Password ─────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(BCRYPT_ROUNDS)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        # Malformed hash or a password over bcrypt's 72-byte limit
        return False


# Used to equalize timing when the account doesn't exist
DUMMY_PASSWORD_HASH = hash_password("dummy-to-prevent-timing-attack")


# ── JWT ──────────────────────────────────────────────────────────────────────
# Every token carries a unique `jti` (so one token can be revoked) and the user's
# `ver` (token_version — bumping it revokes every token the user holds).

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _encode(payload: dict, key: str, lifetime: timedelta) -> str:
    now = _now()
    payload = {**payload, "iat": now, "exp": now + lifetime, "jti": str(uuid.uuid4())}
    return jwt.encode(payload, key, algorithm=settings.algorithm)


def _decode(token: str, key: str, expected_type: str) -> dict:
    payload = jwt.decode(
        token, key,
        algorithms=[settings.algorithm],
        options={"require": ["exp", "iat", "sub", "jti", "type"]},
    )
    if payload.get("type") != expected_type:
        raise JWTError("Invalid token type")
    return payload


def create_access_token(subject: str, token_version: int, extra: dict | None = None) -> str:
    return _encode(
        {"sub": subject, "type": "access", "ver": token_version, **(extra or {})},
        settings.secret_key,
        timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(subject: str, token_version: int, auth_time: int | None = None) -> str:
    """`auth_time` is when the user actually logged in; refreshes keep it so a
    session can't be extended past `max_session_hours`."""
    return _encode(
        {"sub": subject, "type": "refresh", "ver": token_version,
         "auth_time": auth_time if auth_time is not None else int(time.time())},
        settings.refresh_secret_key,
        timedelta(days=settings.refresh_token_expire_days),
    )


def create_mfa_token(subject: str, token_version: int) -> str:
    """Short-lived proof that the password step succeeded; exchanged for real tokens
    once a valid TOTP code is supplied."""
    return _encode(
        {"sub": subject, "type": "mfa", "ver": token_version},
        settings.secret_key,
        timedelta(minutes=settings.mfa_token_expire_minutes),
    )


def decode_access_token(token: str) -> dict:
    """Decode and validate an access token. Raises JWTError on failure.
    Revocation (jti / token_version) is checked against the database by the caller."""
    return _decode(token, settings.secret_key, "access")


def decode_refresh_token(token: str) -> dict:
    payload = _decode(token, settings.refresh_secret_key, "refresh")
    if "auth_time" not in payload:
        raise JWTError("Missing auth_time")
    if time.time() - payload["auth_time"] > settings.max_session_hours * 3600:
        raise JWTError("Session has exceeded its maximum lifetime")
    return payload


def decode_mfa_token(token: str) -> dict:
    return _decode(token, settings.secret_key, "mfa")


def token_expiry(payload: dict) -> datetime:
    return datetime.fromtimestamp(payload["exp"], tz=timezone.utc)


# ── Encryption at rest ───────────────────────────────────────────────────────

def encrypt_secret(value: str) -> str:
    return _fernet.encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    return _fernet.decrypt(value.encode()).decode()


# ── TOTP (MFA) ───────────────────────────────────────────────────────────────

def generate_totp_secret() -> str:
    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret, interval=TOTP_INTERVAL).provisioning_uri(name=email, issuer_name="CodifyAI")


def verify_totp(secret: str, code: str, last_used_step: int | None) -> int | None:
    """Check a 6-digit code against the current step ±1. Returns the matched time
    step, or None. Steps at or before `last_used_step` are rejected (no replay)."""
    code = (code or "").strip().replace(" ", "")
    if not (len(code) == 6 and code.isdigit()):
        return None
    totp = pyotp.TOTP(secret, interval=TOTP_INTERVAL)
    current = int(time.time()) // TOTP_INTERVAL
    for step in (current - 1, current, current + 1):
        if last_used_step is not None and step <= last_used_step:
            continue
        if pyotp.utils.strings_equal(totp.at(step * TOTP_INTERVAL), code):
            return step
    return None
