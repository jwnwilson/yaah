"""role_memory_entries

Revision ID: rolemem01
Revises: orch1msg01
Create Date: 2026-06-16 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "rolemem01"
down_revision: str | None = "orch1msg01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "role_memory_entries",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=True),
        sa.Column("project_id", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_role_memory_entries_owner_id"), "role_memory_entries", ["owner_id"])
    op.create_index(op.f("ix_role_memory_entries_role"), "role_memory_entries", ["role"])
    op.create_index(
        op.f("ix_role_memory_entries_project_id"), "role_memory_entries", ["project_id"])


def downgrade() -> None:
    op.drop_table("role_memory_entries")
