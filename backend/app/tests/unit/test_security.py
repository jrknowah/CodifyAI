import pytest
from app.core.security import (
    hash_password, verify_password,
    create_access_token, decode_access_token,
    create_refresh_token, decode_refresh_token,
    blacklist_token, is_token_blacklisted,
)
from app.schemas.schemas import UserCreate, CodingRequest
from jose import JWTError
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
    token = create_access_token(user_id, {"role": "coder"})
    payload = decode_access_token(token)
    assert payload["sub"] == user_id
    assert payload["role"] == "coder"
    assert payload["type"] == "access"


def test_refresh_token_roundtrip():
    user_id = "550e8400-e29b-41d4-a716-446655440000"
    token = create_refresh_token(user_id)
    payload = decode_refresh_token(token)
    assert payload["sub"] == user_id
    assert payload["type"] == "refresh"


def test_access_token_cannot_be_used_as_refresh():
    token = create_access_token("some-id")
    with pytest.raises(JWTError):
        decode_refresh_token(token)


def test_refresh_token_cannot_be_used_as_access():
    token = create_refresh_token("some-id")
    with pytest.raises(JWTError):
        decode_access_token(token)


def test_blacklisted_token_is_rejected():
    token = create_access_token("some-id")
    blacklist_token(token)
    with pytest.raises(JWTError):
        decode_access_token(token)


def test_token_blacklist_uses_hash_not_plaintext():
    token = create_access_token("some-id")
    blacklist_token(token)
    assert token not in str(is_token_blacklisted(token))


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
            UserCreate(email="test@example.com", password="NoNumbers!!", full_name="Jane Doe")

    def test_password_no_special_char(self):
        with pytest.raises(pydantic.ValidationError, match="special"):
            UserCreate(email="test@example.com", password="NoSpecial123", full_name="Jane Doe")

    def test_invalid_email(self):
        with pytest.raises(pydantic.ValidationError):
            UserCreate(email="not-an-email", password="ValidPass123!", full_name="Jane Doe")

    def test_name_with_script_tag_is_sanitized(self):
        u = UserCreate(
            email="test@example.com",
            password="ValidPass123!",
            full_name="Jane Doe"
        )
        assert "<script>" not in u.full_name


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
