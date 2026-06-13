from sqlalchemy import create_engine, inspect

from adapters.database.orm import Base


def test_notifications_table_columns():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("notifications")}
    assert {"id", "owner_id", "source", "category", "severity", "title", "body",
            "run_id", "work_item_id", "project_id", "action", "read_at", "resolved_at",
            "created_at"} <= cols
