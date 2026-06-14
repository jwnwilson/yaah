"""messages table and work_items.assignee_agent_id

Revision ID: orch1msg01
Revises: a6b2memory02
Create Date: 2026-06-14 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "orch1msg01"
down_revision: str | None = "a6b2memory02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("sender_kind", sa.String(length=10), nullable=False),
        sa.Column("sender_agent_id", sa.String(length=32), nullable=True),
        sa.Column("recipient_kind", sa.String(length=10), nullable=False),
        sa.Column("recipient_agent_id", sa.String(length=32), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=True),
        sa.Column("work_item_id", sa.String(length=32), nullable=True),
        sa.Column("project_id", sa.String(length=32), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_messages_owner_id"), "messages", ["owner_id"])
    op.create_index(op.f("ix_messages_sender_agent_id"), "messages", ["sender_agent_id"])
    op.create_index(
        op.f("ix_messages_recipient_agent_id"), "messages", ["recipient_agent_id"]
    )
    op.create_index(op.f("ix_messages_run_id"), "messages", ["run_id"])
    op.add_column(
        "work_items",
        sa.Column("assignee_agent_id", sa.String(length=32), nullable=True),
    )
    op.create_index(
        op.f("ix_work_items_assignee_agent_id"), "work_items", ["assignee_agent_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_work_items_assignee_agent_id"), table_name="work_items")
    op.drop_column("work_items", "assignee_agent_id")
    op.drop_index(op.f("ix_messages_run_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_recipient_agent_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_sender_agent_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_owner_id"), table_name="messages")
    op.drop_table("messages")
