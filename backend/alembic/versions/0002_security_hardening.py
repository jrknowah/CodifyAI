"""Security hardening: token revocation, MFA, PHI removal, immutable audit log

- users: token_version (revoke all tokens), TOTP MFA columns
- revoked_tokens: per-token denylist (logout, refresh rotation)
- encounters: drop `summary` and strip `reason` from stored codes — both are
  model-written text about the note and can contain PHI
- audit_logs: new actions; trigger blocking UPDATE / DELETE / TRUNCATE

Revision ID: 0002_security_hardening
Revises: 0001_baseline
Create Date: 2026-10-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_security_hardening"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_AUDIT_ACTIONS = [
    "login_failed", "account_locked", "view_history", "view_audit_log", "user_updated",
    "user_unlocked", "mfa_enabled", "mfa_disabled", "mfa_reset", "refresh_token_reuse",
]

# Kept in sync with app.models.models.AUDIT_LOG_IMMUTABLE_SQL (duplicated so this
# migration doesn't change if the model module does).
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


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE can't run inside a transaction block
    with op.get_context().autocommit_block():
        for value in NEW_AUDIT_ACTIONS:
            op.execute(f"ALTER TYPE auditaction ADD VALUE IF NOT EXISTS '{value}'")

    op.add_column("users", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("mfa_secret_encrypted", sa.String(512), nullable=True))
    op.add_column("users", sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("mfa_last_used_step", sa.BigInteger(), nullable=True))

    op.create_table(
        "revoked_tokens",
        sa.Column("jti", sa.String(36), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_revoked_tokens_expires_at", "revoked_tokens", ["expires_at"])

    # Purge PHI-bearing free text from existing encounters
    op.drop_column("encounters", "summary")
    op.execute("""
        UPDATE encounters
        SET codes = COALESCE(
            (SELECT json_agg(elem::jsonb - 'reason') FROM json_array_elements(codes) AS elem),
            '[]'::json
        )
    """)

    for stmt in AUDIT_LOG_IMMUTABLE_SQL:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_logs_no_truncate ON audit_logs")
    op.execute("DROP TRIGGER IF EXISTS audit_logs_no_update_delete ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS audit_logs_immutable()")
    # The purged summaries/reasons are gone for good; the column comes back empty.
    op.add_column("encounters", sa.Column("summary", sa.Text(), nullable=False, server_default=""))
    op.drop_index("ix_revoked_tokens_expires_at", table_name="revoked_tokens")
    op.drop_table("revoked_tokens")
    op.drop_column("users", "mfa_last_used_step")
    op.drop_column("users", "mfa_enabled")
    op.drop_column("users", "mfa_secret_encrypted")
    op.drop_column("users", "token_version")
    # Postgres can't remove enum values; the extra audit actions stay.
