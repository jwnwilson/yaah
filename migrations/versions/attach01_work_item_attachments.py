"""work_item_attachments table

Revision ID: attach01
Revises: orch1msg01
Create Date: 2026-06-16 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "attach01"
down_revision: str | None = "orch1msg01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "work_item_attachments",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("work_item_id", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=300), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=400), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        op.f("ix_work_item_attachments_owner_id"), "work_item_attachments", ["owner_id"]
    )
    op.create_index(
        op.f("ix_work_item_attachments_work_item_id"),
        "work_item_attachments",
        ["work_item_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_work_item_attachments_work_item_id"), "work_item_attachments")
    op.drop_index(op.f("ix_work_item_attachments_owner_id"), "work_item_attachments")
    op.drop_table("work_item_attachments")
