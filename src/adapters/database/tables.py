from sqlalchemy import JSON, Column, DateTime, Float, MetaData, String, Table, Text

metadata = MetaData()

projects = Table(
    "projects",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("owner_id", String(64), nullable=False, index=True),
    Column("name", String(200), nullable=False),
    Column("repo_url", String(500)),
    Column("local_path", String(500)),
    Column("team_id", String(32)),
    Column("autonomy", String(20), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

work_items = Table(
    "work_items",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("project_id", String(32), nullable=False, index=True),
    Column("kind", String(10), nullable=False),
    Column("parent_id", String(32), index=True),
    Column("title", String(300), nullable=False),
    Column("body", Text, nullable=False, default=""),
    Column("acceptance_criteria", JSON, nullable=False),
    Column("status", String(20), nullable=False, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

teams = Table(
    "teams",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("owner_id", String(64), nullable=False, index=True),
    Column("name", String(200), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

agent_definitions = Table(
    "agent_definitions",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("team_id", String(32), nullable=False, index=True),
    Column("role", String(20), nullable=False),
    Column("name", String(100), nullable=False),
    Column("persona", Text, nullable=False, default=""),
    Column("model_alias", String(100), nullable=False),
    Column("runtime", String(50), nullable=False),
)

runs = Table(
    "runs",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("task_id", String(32), nullable=False, index=True),
    Column("team_id", String(32), nullable=False),
    Column("status", String(30), nullable=False, index=True),
    Column("stage", String(30)),
    Column("branch", String(200)),
    Column("pr_url", String(500)),
    Column("cost_usd", Float, nullable=False, default=0.0),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
