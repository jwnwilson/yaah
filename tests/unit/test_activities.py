from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from adapters.runtime.fake import FakeAgentRuntime
from interactors.temporal.activities import RunActivities
from domain.models import Run, RunStage, RunStatus


def _factory():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def _seed_run(factory) -> str:
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        run = uow.runs.create(Run(owner_id="u1", task_id="t1", team_id="tm1"))
    return run.id


def test_persist_run_state_updates_row():
    factory = _factory()
    run_id = _seed_run(factory)
    acts = RunActivities(factory, FakeAgentRuntime())
    acts.persist_run_state(
        {
            "run_id": run_id,
            "owner_id": "u1",
            "status": RunStatus.RUNNING,
            "stage": RunStage.PLAN,
            "cost_usd": 1.0,
        }
    )
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        run = uow.runs.get(run_id)
    assert run.status == "running" and run.stage == "plan" and run.cost_usd == 1.0


def test_run_stage_records_events_and_returns_result():
    factory = _factory()
    run_id = _seed_run(factory)
    acts = RunActivities(factory, FakeAgentRuntime())
    result = acts.run_stage(
        {
            "run_id": run_id,
            "owner_id": "u1",
            "stage": RunStage.PLAN,
            "task_title": "T",
            "acceptance_criteria": [],
            "workspace_path": "/tmp/x",
        }
    )
    assert result["outcome"] == "ok"
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        page = uow.run_events.list(filters={"run_id": run_id})
    assert page.total >= 1
