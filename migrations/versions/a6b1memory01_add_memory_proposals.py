"""add memory_proposals

Revision ID: a6b1memory01
Revises: b196b5b90b23
Create Date: 2026-06-14 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a6b1memory01"
down_revision: str | None = "b196b5b90b23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memory_proposals",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("branch", sa.String(length=200), nullable=False),
        sa.Column("diff", sa.Text(), nullable=False),
        sa.Column("files", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_memory_proposals_owner_id"), "memory_proposals",
                    ["owner_id"], unique=False)
    op.create_index(op.f("ix_memory_proposals_run_id"), "memory_proposals",
                    ["run_id"], unique=False)
    op.create_index(op.f("ix_memory_proposals_project_id"), "memory_proposals",
                    ["project_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_memory_proposals_project_id"), table_name="memory_proposals")
    op.drop_index(op.f("ix_memory_proposals_run_id"), table_name="memory_proposals")
    op.drop_index(op.f("ix_memory_proposals_owner_id"), table_name="memory_proposals")
    op.drop_table("memory_proposals")
