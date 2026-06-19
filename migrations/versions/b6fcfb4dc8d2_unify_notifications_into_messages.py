"""unify notifications into messages

Revision ID: b6fcfb4dc8d2
Revises: bk1pos01
Create Date: 2026-06-19 11:54:49.403992

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b6fcfb4dc8d2'
down_revision: str | None = 'bk1pos01'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'messages',
        sa.Column('severity', sa.String(length=20), server_default='info', nullable=False),
    )
    op.drop_table('notifications')


def downgrade() -> None:
    op.drop_column('messages', 'severity')
    op.create_table('notifications',
    sa.Column('id', sa.VARCHAR(length=32), autoincrement=False, nullable=False),
    sa.Column('owner_id', sa.VARCHAR(length=64), autoincrement=False, nullable=False),
    sa.Column('source', sa.VARCHAR(length=10), autoincrement=False, nullable=False),
    sa.Column('category', sa.VARCHAR(length=20), autoincrement=False, nullable=False),
    sa.Column('severity', sa.VARCHAR(length=20), autoincrement=False, nullable=False),
    sa.Column('title', sa.VARCHAR(length=300), autoincrement=False, nullable=False),
    sa.Column('body', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('run_id', sa.VARCHAR(length=32), autoincrement=False, nullable=True),
    sa.Column('work_item_id', sa.VARCHAR(length=32), autoincrement=False, nullable=True),
    sa.Column('project_id', sa.VARCHAR(length=32), autoincrement=False, nullable=True),
    sa.Column('action', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('read_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('resolved_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('notifications_pkey'))
    )
    op.create_index(op.f('ix_notifications_run_id'), 'notifications', ['run_id'], unique=False)
    op.create_index(op.f('ix_notifications_owner_id'), 'notifications', ['owner_id'], unique=False)
    op.create_index(op.f('ix_notifications_category'), 'notifications', ['category'], unique=False)
    # ### end Alembic commands ###
