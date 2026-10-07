import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    String, Boolean, DateTime, Integer, BigInteger,
    ForeignKey, JSON, Enum as SAEnum, Index, DDL, event
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
    urgent_care = "urgent-care"


class AuditAction(str, enum.Enum):
    login = "login"
    logout = "logout"
    analyze = "analyze"
    export = "export"
    user_created = "user_created"
    password_changed = "password_changed"
    login_failed = "login_failed"
    account_locked = "account_locked"
    view_history = "view_history"
    view_audit_log = "view_audit_log"
    user_updated = "user_updated"
    user_unlocked = "user_unlocked"
    mfa_enabled = "mfa_enabled"
    mfa_disabled = "mfa_disabled"
    mfa_reset = "mfa_reset"
    refresh_token_reuse = "refresh_token_reuse"


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

    # Bumping this revokes every token issued to the user (password change,
    # deactivation, refresh-token reuse).
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # TOTP MFA — secret is Fernet-encrypted at rest
    mfa_secret_encrypted: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_last_used_step: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

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
    """
    One coding session — a clinical note in, codes out.

    Only de-identified results are stored: code, type, official description and
    confidence. Free text the model writes about the note (per-code reasons, the
    summary) can quote PHI, so it is returned to the coder but never persisted.
    """
    __tablename__ = "encounters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    facility_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("facilities.id"), nullable=True)

    # Note stored as hash only (PHI protection) — full text never persisted
    note_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    note_length: Mapped[int] = mapped_column(Integer, nullable=False)
    facility_type: Mapped[FacilityType] = mapped_column(SAEnum(FacilityType), default=FacilityType.post_acute)

    # Results
    codes: Mapped[list] = mapped_column(JSON, nullable=False)       # [{code, type, description, confidence, modifiers}]
    # E/M suggestion (urgent care): levels and computed checks only — no support text
    em_level: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Suggestions the server dropped (bad format, unlicensed CPT) and why
    flagged_codes: Mapped[list | None] = mapped_column(JSON, nullable=True)
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
    A database trigger rejects UPDATE, DELETE and TRUNCATE on this table.
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


class RevokedToken(Base):
    """Denylist of individually revoked JWTs (logout, rotated refresh tokens).
    Rows can be pruned once `expires_at` has passed."""
    __tablename__ = "revoked_tokens"

    jti: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ── Audit log immutability ────────────────────────────────────────────────────
# Shared with the Alembic migration so tests (create_all) get the same protection.

AUDIT_LOG_IMMUTABLE_SQL = [
    """
    CREATE OR REPLACE FUNCTION audit_logs_immutable() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'audit_logs is append-only (% blocked)', TG_OP;
    END;
    $$ LANGUAGE plpgsql
    """,
    """
    CREATE TRIGGER audit_logs_no_update_delete
    BEFORE UPDATE OR DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable()
    """,
    """
    CREATE TRIGGER audit_logs_no_truncate
    BEFORE TRUNCATE ON audit_logs
    FOR EACH STATEMENT EXECUTE FUNCTION audit_logs_immutable()
    """,
]

for _stmt in AUDIT_LOG_IMMUTABLE_SQL:
    # DDL() applies %-formatting, so escape the literal % in the RAISE message
    event.listen(
        AuditLog.__table__, "after_create",
        DDL(_stmt.replace("%", "%%")).execute_if(dialect="postgresql"),
    )
