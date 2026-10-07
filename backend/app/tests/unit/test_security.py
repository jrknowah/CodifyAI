import pytest
import time
import pyotp
from app.core.security import (
    hash_password, verify_password,
    create_access_token, decode_access_token,
    create_refresh_token, decode_refresh_token,
    create_mfa_token, decode_mfa_token,
    encrypt_secret, decrypt_secret,
    generate_totp_secret, verify_totp, TOTP_INTERVAL,
    JWTError,
)
from app.core.config import settings
from app.schemas.schemas import UserCreate, CodingRequest
import pydantic


# ── Password hashing ──────────────────────────────────────────────────────────

def test_hash_password_is_not_plaintext():
    hashed = hash_password("MyPassword123!")
    assert hashed != "MyPassword123!"
    assert len(hashed) > 20


def test_verify_correct_password():
    hashed = hash_password("MyPassword123!")
    assert verify_password("MyPassword123!", hashed) is True


def test_verify_wrong_password():
    hashed = hash_password("MyPassword123!")
    assert verify_password("WrongPassword!", hashed) is False


# ── JWT ───────────────────────────────────────────────────────────────────────

def test_access_token_roundtrip():
    user_id = "550e8400-e29b-41d4-a716-446655440000"
    token = create_access_token(user_id, 0, {"role": "coder"})
    payload = decode_access_token(token)
    assert payload["sub"] == user_id
    assert payload["role"] == "coder"
    assert payload["type"] == "access"


def test_refresh_token_roundtrip():
    user_id = "550e8400-e29b-41d4-a716-446655440000"
    token = create_refresh_token(user_id, 0)
    payload = decode_refresh_token(token)
    assert payload["sub"] == user_id
    assert payload["type"] == "refresh"


def test_access_token_cannot_be_used_as_refresh():
    token = create_access_token("some-id", 0)
    with pytest.raises(JWTError):
        decode_refresh_token(token)


def test_refresh_token_cannot_be_used_as_access():
    token = create_refresh_token("some-id", 0)
    with pytest.raises(JWTError):
        decode_access_token(token)


def test_tokens_have_unique_jti_and_version():
    a = decode_access_token(create_access_token("some-id", 3))
    b = decode_access_token(create_access_token("some-id", 3))
    assert a["jti"] != b["jti"]
    assert a["ver"] == 3


def test_mfa_token_is_not_an_access_token():
    token = create_mfa_token("some-id", 0)
    assert decode_mfa_token(token)["type"] == "mfa"
    with pytest.raises(JWTError):
        decode_access_token(token)


def test_refresh_token_rejected_past_max_session_lifetime():
    too_old = int(time.time()) - settings.max_session_hours * 3600 - 60
    token = create_refresh_token("some-id", 0, auth_time=too_old)
    with pytest.raises(JWTError):
        decode_refresh_token(token)


def test_refresh_token_keeps_auth_time():
    auth_time = int(time.time()) - 3600
    payload = decode_refresh_token(create_refresh_token("some-id", 0, auth_time=auth_time))
    assert payload["auth_time"] == auth_time


def test_alg_none_token_rejected():
    import jwt as pyjwt
    forged = pyjwt.encode(
        {"sub": "x", "type": "access", "jti": "j", "ver": 0, "iat": int(time.time()),
         "exp": int(time.time()) + 60},
        key=None, algorithm="none",
    )
    with pytest.raises(JWTError):
        decode_access_token(forged)


def test_verify_password_handles_overlong_input():
    assert verify_password("x" * 100, hash_password("MyPassword123!")) is False


# ── Encryption & TOTP ─────────────────────────────────────────────────────────

def test_encrypt_secret_roundtrip():
    enc = encrypt_secret("JBSWY3DPEHPK3PXP")
    assert "JBSWY3DPEHPK3PXP" not in enc
    assert decrypt_secret(enc) == "JBSWY3DPEHPK3PXP"


def test_verify_totp_accepts_current_code():
    secret = generate_totp_secret()
    code = pyotp.TOTP(secret).now()
    assert verify_totp(secret, code, None) is not None


def test_verify_totp_rejects_replay():
    secret = generate_totp_secret()
    code = pyotp.TOTP(secret).now()
    step = verify_totp(secret, code, None)
    assert verify_totp(secret, code, step) is None


def test_verify_totp_rejects_garbage_and_old_codes():
    secret = generate_totp_secret()
    assert verify_totp(secret, "abc123", None) is None
    old = pyotp.TOTP(secret).at(time.time() - 10 * TOTP_INTERVAL)
    assert verify_totp(secret, old, None) is None


# ── Input validation ──────────────────────────────────────────────────────────

class TestUserCreateValidation:
    def test_valid_user(self):
        u = UserCreate(email="test@example.com", password="SecurePass123!", full_name="Jane Doe")
        assert u.email == "test@example.com"

    def test_password_too_short(self):
        with pytest.raises(pydantic.ValidationError, match="12 characters"):
            UserCreate(email="test@example.com", password="Short1!", full_name="Jane Doe")

    def test_password_no_uppercase(self):
        with pytest.raises(pydantic.ValidationError, match="uppercase"):
            UserCreate(email="test@example.com", password="lowercase123!", full_name="Jane Doe")

    def test_password_no_number(self):
        with pytest.raises(pydantic.ValidationError, match="number"):
            UserCreate(email="test@example.com", password="NoNumbersHere!!", full_name="Jane Doe")

    def test_password_too_long_for_bcrypt(self):
        with pytest.raises(pydantic.ValidationError, match="72 bytes"):
            UserCreate(email="test@example.com", password="Aa1!" + "x" * 80, full_name="Jane Doe")

    def test_name_with_apostrophe_is_allowed(self):
        u = UserCreate(email="test@example.com", password="ValidPass123!", full_name="Mary O'Brien")
        assert u.full_name == "Mary O'Brien"

    def test_name_with_markup_is_rejected(self):
        with pytest.raises(pydantic.ValidationError, match="invalid characters"):
            UserCreate(email="test@example.com", password="ValidPass123!", full_name="<script>x</script>")

    def test_password_no_special_char(self):
        with pytest.raises(pydantic.ValidationError, match="special"):
            UserCreate(email="test@example.com", password="NoSpecial123", full_name="Jane Doe")

    def test_invalid_email(self):
        with pytest.raises(pydantic.ValidationError):
            UserCreate(email="not-an-email", password="ValidPass123!", full_name="Jane Doe")


class TestCodingRequestValidation:
    def test_valid_request(self):
        r = CodingRequest(clinical_note="Patient is a 70-year-old male recovering from hip surgery with hypertension.", facility_type="post-acute")
        assert r.facility_type == "post-acute"

    def test_note_too_short(self):
        with pytest.raises(pydantic.ValidationError, match="30 characters"):
            CodingRequest(clinical_note="Too short", facility_type="post-acute")

    def test_note_too_long(self):
        with pytest.raises(pydantic.ValidationError, match="10,000"):
            CodingRequest(clinical_note="x" * 10_001, facility_type="post-acute")

    def test_invalid_facility_type(self):
        with pytest.raises(pydantic.ValidationError):
            CodingRequest(clinical_note="Valid note " * 5, facility_type="hospital")
