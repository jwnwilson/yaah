"""work_item chat_session_id

Revision ID: chatsid01
Revises: b6fcfb4dc8d2
Create Date: 2026-06-19

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "chatsid01"
down_revision: str | None = "b6fcfb4dc8d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "work_items",
        sa.Column("chat_session_id", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ix_work_items_chat_session_id", "work_items", ["chat_session_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_work_items_chat_session_id", table_name="work_items")
    op.drop_column("work_items", "chat_session_id")
