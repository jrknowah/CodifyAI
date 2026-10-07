"""Urgent care: facility type, E/M suggestion and flagged-code columns

Revision ID: 0003_urgent_care
Revises: 0002_security_hardening
Create Date: 2026-10-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_urgent_care"
down_revision: Union[str, None] = "0002_security_hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLAlchemy stores enum member names, so the label is urgent_care
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE facilitytype ADD VALUE IF NOT EXISTS 'urgent_care'")
    op.add_column("encounters", sa.Column("em_level", sa.JSON(), nullable=True))
    op.add_column("encounters", sa.Column("flagged_codes", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("encounters", "flagged_codes")
    op.drop_column("encounters", "em_level")
    # Postgres can't drop an enum value; urgent_care stays in facilitytype.
