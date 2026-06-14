"""memory proposal apply fields

Revision ID: a6b2memory02
Revises: a6b1memory01
Create Date: 2026-06-14 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a6b2memory02"
down_revision: str | None = "a6b1memory01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("memory_proposals",
                  sa.Column("pr_url", sa.String(length=500), nullable=True))
    op.add_column("memory_proposals",
                  sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("memory_proposals", "resolved_at")
    op.drop_column("memory_proposals", "pr_url")
