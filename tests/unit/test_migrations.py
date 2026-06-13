"""Alembic migrations must stay in sync with the ORM metadata.

If someone changes `adapters/database/orm.py` without generating a migration, the head
schema will diverge from the models and this test fails — catching the drift that the old
`create_all`-only setup silently tolerated.
"""

import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from adapters.database.orm import Base

_ROOT = Path(__file__).resolve().parents[2]


def test_migrations_upgrade_matches_orm_metadata(monkeypatch):
    # Arrange: a throwaway on-disk SQLite DB, with alembic pointed at it via YAAH_DATABASE_URL.
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{Path(tmp) / 'migrated.db'}"
        monkeypatch.setenv("YAAH_DATABASE_URL", url)
        config = Config(str(_ROOT / "alembic.ini"))

        # Act: apply every migration from base to head.
        command.upgrade(config, "head")

        # Assert: the migrated schema matches the ORM (ignoring alembic's bookkeeping table).
        engine = create_engine(url)
        migrated_tables = set(inspect(engine).get_table_names()) - {"alembic_version"}
        engine.dispose()

    assert migrated_tables == set(Base.metadata.tables.keys())
