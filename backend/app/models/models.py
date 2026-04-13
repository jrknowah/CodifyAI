import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    String, Boolean, DateTime, Text, Float, Integer,
    ForeignKey, JSON, Enum as SAEnum, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.session import Base
import enum


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Enums ─────────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    admin = "admin"
    coder = "coder"
    viewer = "viewer"


class FacilityType(str, enum.Enum):
    post_acute = "post-acute"
    snf = "snf"
    home_health = "home-health"
    irf = "irf"


class AuditAction(str, enum.Enum):
    login = "login"
    logout = "logout"
    analyze = "analyze"
    export = "export"
    user_created = "user_created"
    password_changed = "password_changed"


# ── Models ────────────────────────────────────────────────────────────────────

class Facility(Base):
    __tablename__ = "facilities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    facility_type: Mapped[FacilityType] = mapped_column(SAEnum(FacilityType), nullable=False)
    npi: Mapped[str | None] = mapped_column(String(10), unique=True, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    users: Mapped[list["User"]] = relationship("User", back_populates="facility")
    encounters: Mapped[list["Encounter"]] = relationship("Encounter", back_populates="facility")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), default=UserRole.coder)
    facility_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("facilities.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    facility: Mapped["Facility | None"] = relationship("Facility", back_populates="users")
    encounters: Mapped[list["Encounter"]] = relationship("Encounter", back_populates="user")
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="user")

    def is_locked(self) -> bool:
        if self.locked_until and self.locked_until > utcnow():
            return True
        return False


class Encounter(Base):
    """One coding session — a clinical note in, codes out."""
    __tablename__ = "encounters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    facility_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("facilities.id"), nullable=True)

    # Note stored as hash only (PHI protection) — full text never persisted
    note_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    note_length: Mapped[int] = mapped_column(Integer, nullable=False)
    facility_type: Mapped[FacilityType] = mapped_column(SAEnum(FacilityType), default=FacilityType.post_acute)

    # Results
    codes: Mapped[dict] = mapped_column(JSON, nullable=False)       # List of code objects
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    code_count: Mapped[int] = mapped_column(Integer, nullable=False)
    top_code: Mapped[str] = mapped_column(String(20), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship("User", back_populates="encounters")
    facility: Mapped["Facility | None"] = relationship("Facility", back_populates="encounters")

    __table_args__ = (
        Index("ix_encounters_user_id_created", "user_id", "created_at"),
    )


class AuditLog(Base):
    """
    Append-only HIPAA audit trail.
    NEVER update or delete rows from this table.
    """
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[AuditAction] = mapped_column(SAEnum(AuditAction), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # encounter_id etc.
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)   # supports IPv6
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)            # extra context
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User | None"] = relationship("User", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_logs_user_id_created", "user_id", "created_at"),
        Index("ix_audit_logs_action", "action"),
    )
