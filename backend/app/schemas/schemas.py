from pydantic import AfterValidator, BaseModel, EmailStr, field_validator, ConfigDict
from typing import Annotated, Optional, List, Literal
from datetime import datetime
from uuid import UUID
import re


# ── Shared validators ─────────────────────────────────────────────────────────

def validate_password_policy(v: str) -> str:
    if len(v) < 12:
        raise ValueError("Password must be at least 12 characters.")
    if len(v.encode("utf-8")) > 72:
        raise ValueError("Password must be at most 72 bytes.")
    if not re.search(r"[A-Z]", v):
        raise ValueError("Password must contain an uppercase letter.")
    if not re.search(r"[0-9]", v):
        raise ValueError("Password must contain a number.")
    if not re.search(r"[^A-Za-z0-9]", v):
        raise ValueError("Password must contain a special character.")
    return v


def validate_full_name(v: str) -> str:
    # Whitelist validation rather than HTML-escaping: escaping turned the apostrophe
    # in names like O'Brien into "&#x27;", which the whitelist then rejected.
    v = re.sub(r"\s+", " ", v.strip())
    if len(v) < 2 or len(v) > 255:
        raise ValueError("Full name must be 2–255 characters.")
    if not re.match(r"^[A-Za-z\s\-'.]+$", v):
        raise ValueError("Full name contains invalid characters.")
    return v


Password = Annotated[str, AfterValidator(validate_password_policy)]
FullName = Annotated[str, AfterValidator(validate_full_name)]
UserRoleName = Literal["admin", "coder", "viewer"]


# ── Auth ──────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    password: Password
    full_name: FullName


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    mfa_enabled: bool
    mfa_enrollment_required: bool = False
    last_login: Optional[datetime]
    created_at: datetime


class LoginResponse(BaseModel):
    """Either a session (access_token set, refresh token in an httpOnly cookie) or,
    for MFA users, an mfa_token to exchange at /auth/mfa/verify."""
    access_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: Optional[int] = None  # seconds
    mfa_required: bool = False
    mfa_token: Optional[str] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: Password


class MfaVerifyRequest(BaseModel):
    mfa_token: str
    code: str


class MfaSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class MfaCodeRequest(BaseModel):
    code: str


class MfaDisableRequest(BaseModel):
    password: str
    code: str


# ── Admin ─────────────────────────────────────────────────────────────────────

class AdminUserCreate(UserCreate):
    role: UserRoleName = "coder"
    facility_id: Optional[UUID] = None


class AdminUserUpdate(BaseModel):
    full_name: Optional[FullName] = None
    role: Optional[UserRoleName] = None
    is_active: Optional[bool] = None
    facility_id: Optional[UUID] = None


class AdminUserOut(UserOut):
    facility_id: Optional[UUID]
    failed_login_attempts: int
    locked_until: Optional[datetime]


# ── Coding ────────────────────────────────────────────────────────────────────

class CodingRequest(BaseModel):
    clinical_note: str
    facility_type: str = "post-acute"

    @field_validator("clinical_note")
    @classmethod
    def validate_note(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 30:
            raise ValueError("Clinical note must be at least 30 characters.")
        if len(v) > 10_000:
            raise ValueError("Clinical note must not exceed 10,000 characters.")
        return v

    @field_validator("facility_type")
    @classmethod
    def validate_facility_type(cls, v: str) -> str:
        allowed = {"post-acute", "snf", "home-health", "irf"}
        if v not in allowed:
            raise ValueError(f"facility_type must be one of: {allowed}")
        return v


class CodeResult(BaseModel):
    code: str
    type: str
    description: str
    confidence: float
    reason: str

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("Confidence must be between 0 and 1.")
        return round(v, 3)

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        v = v.strip().upper()
        if len(v) > 20:
            raise ValueError("Code too long.")
        return v


class CodingResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    encounter_id: UUID
    codes: List[CodeResult]
    summary: str
    model_used: str
    code_count: int
    created_at: datetime


class EncounterSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    id: UUID
    note_length: int
    facility_type: str
    code_count: int
    top_code: str
    model_used: str
    created_at: datetime


# ── Audit ─────────────────────────────────────────────────────────────────────

class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    user_id: Optional[UUID]
    action: str
    resource_id: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    success: bool
    detail: Optional[dict]
    created_at: datetime


# ── Common ────────────────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str

class HealthResponse(BaseModel):
    status: str
    version: str
    env: str
