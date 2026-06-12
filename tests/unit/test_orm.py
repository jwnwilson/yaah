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
                created_at=__import__("domain.models", fromlist=["utc_now"]).utc_now(),
            )
        )
        session.commit()
        row = session.execute(select(ProjectRow)).scalar_one()
        assert row.owner_id == "u1"


def test_work_item_row_has_owner_id_column():
    assert "owner_id" in WorkItemRow.__table__.columns
