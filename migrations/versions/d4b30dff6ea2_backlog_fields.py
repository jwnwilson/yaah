"""backlog fields

Revision ID: d4b30dff6ea2
Revises: da35de1e3b1a
Create Date: 2026-06-18 15:47:35.901598

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4b30dff6ea2'
down_revision: str | None = 'da35de1e3b1a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("max_concurrent_runs", sa.Integer(), nullable=False, server_default="2"),
    )
    op.add_column(
        "work_items",
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("work_items", "active")
    op.drop_column("projects", "max_concurrent_runs")
