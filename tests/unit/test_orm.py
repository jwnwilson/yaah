from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from adapters.database.orm import Base, ProjectRow, WorkItemRow


def test_create_all_and_roundtrip():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            ProjectRow(
                id="a" * 32,
                owner_id="u1",
                name="p",
                repo_url="r",
                local_path=None,
                team_id=None,
                autonomy="gated_all",
                created_at=__import__("domain.base", fromlist=["utc_now"]).utc_now(),
            )
        )
        session.commit()
        row = session.execute(select(ProjectRow)).scalar_one()
        assert row.owner_id == "u1"


def test_work_item_row_has_owner_id_column():
    assert "owner_id" in WorkItemRow.__table__.columns


def test_capability_rows_roundtrip():
    from adapters.database.engine import make_engine, make_session_factory
    from adapters.database.orm import AgentDefinitionRow, Base, SkillRow

    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = make_session_factory(engine)()
    s.add(SkillRow(id="s1", owner_id="u", name="pytest", description="", source="x",
                   created_at=__import__("datetime").datetime.now()))
    s.add(AgentDefinitionRow(id="a1", team_id="t", role="lead", name="L", persona="",
                             model_alias="m", runtime="claude_code", purpose="p",
                             system_prompt="sp", allowed_tools=["Read"], skill_ids=["s1"],
                             mcp_server_ids=[], secret_ids=[]))
    s.commit()
    assert s.get(SkillRow, "s1").name == "pytest"
    assert s.get(AgentDefinitionRow, "a1").skill_ids == ["s1"]


def test_workitem_and_project_backlog_columns_roundtrip():
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from adapters.database.orm import Base, ProjectRow, WorkItemRow
    from domain.base import new_id, utc_now

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(ProjectRow(
            id=new_id(), owner_id="o", name="p", repo_url="r", local_path=None,
            team_id=None, autonomy="gated_all", max_concurrent_runs=3, created_at=utc_now(),
        ))
        session.add(WorkItemRow(
            id=new_id(), owner_id="o", project_id="p", kind="epic", parent_id=None,
            title="E", body="", acceptance_criteria=[], status="draft",
            assignee_agent_id=None, active=True, created_at=utc_now(), updated_at=utc_now(),
        ))
        session.commit()
        proj = session.execute(select(ProjectRow)).scalar_one()
        item = session.execute(select(WorkItemRow)).scalar_one()
        assert proj.max_concurrent_runs == 3
        assert item.active is True
