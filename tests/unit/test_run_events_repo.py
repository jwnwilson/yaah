from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.models import RunEvent, RunEventType, RunStage


def _uow():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return SqlUnitOfWork(make_session_factory(engine), required_filters={"owner_id": "u1"})


def test_create_and_list_run_events_owner_scoped():
    uow = _uow()
    with uow.transaction():
        uow.run_events.create(RunEvent(run_id="r1", owner_id="u1", stage=RunStage.PLAN,
                                       type=RunEventType.STAGE_STARTED, message="a"))
        uow.run_events.create(RunEvent(run_id="r1", owner_id="u1", stage=RunStage.PLAN,
                                       type=RunEventType.STAGE_COMPLETED, message="b"))
        page = uow.run_events.list(filters={"run_id": "r1"}, order_by="created_at")
    assert page.total == 2
    assert [e.type for e in page.results] == ["stage_started", "stage_completed"]


def test_run_events_cross_tenant_hidden():
    uow = _uow()
    with uow.transaction():
        uow.run_events.create(RunEvent(run_id="r1", owner_id="u1", type=RunEventType.AGENT_EVENT))
    other = SqlUnitOfWork(uow._session_factory, required_filters={"owner_id": "u2"})
    with other.transaction():
        page = other.run_events.list(filters={"run_id": "r1"})
    assert page.total == 0
