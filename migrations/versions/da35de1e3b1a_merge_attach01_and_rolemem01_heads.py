"""merge attach01 and rolemem01 heads

Revision ID: da35de1e3b1a
Revises: attach01, rolemem01
Create Date: 2026-06-16 13:59:42.994874

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'da35de1e3b1a'
down_revision: str | None = ('attach01', 'rolemem01')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
