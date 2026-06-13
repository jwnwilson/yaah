from sqlalchemy import create_engine, inspect

from adapters.database.orm import Base


def test_usage_records_table_and_run_token_columns_exist():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    insp = inspect(engine)
    assert "usage_records" in insp.get_table_names()
    usage_cols = {c["name"] for c in insp.get_columns("usage_records")}
    assert {"run_id", "work_item_id", "project_id", "stage", "agent_role",
            "model_id", "input_tokens", "cost_usd", "dedupe_key"} <= usage_cols
    run_cols = {c["name"] for c in insp.get_columns("runs")}
    assert {"input_tokens", "output_tokens", "cache_read_tokens",
            "cache_creation_tokens"} <= run_cols
