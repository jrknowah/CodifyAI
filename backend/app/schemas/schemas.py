from pydantic import BaseModel, EmailStr, field_validator, model_validator, ConfigDict
from typing import Optional, List
from datetime import datetime
from uuid import UUID
import re
import html


# ── Shared validators ─────────────────────────────────────────────────────────

def sanitize_text(v: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    cleaned = html.escape(v.strip())
    # Collapse multiple whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned


# ── Auth ──────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    facility_id: Optional[UUID] = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters.")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain an uppercase letter.")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain a number.")
        if not re.search(r"[^A-Za-z0-9]", v):
            raise ValueError("Password must contain a special character.")
        return v

    @field_validator("full_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = sanitize_text(v)
        if len(v) < 2 or len(v) > 255:
            raise ValueError("Full name must be 2–255 characters.")
        if not re.match(r"^[A-Za-z\s\-'.]+$", v):
            raise ValueError("Full name contains invalid characters.")
        return v


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
    last_login: Optional[datetime]
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters.")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Must contain an uppercase letter.")
        if not re.search(r"[0-9]", v):
            raise ValueError("Must contain a number.")
        if not re.search(r"[^A-Za-z0-9]", v):
            raise ValueError("Must contain a special character.")
        return v


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
    encounter_id: UUID
    codes: List[CodeResult]
    summary: str
    model_used: str
    code_count: int
    created_at: datetime


class EncounterSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
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
    action: str
    resource_id: Optional[str]
    ip_address: Optional[str]
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
