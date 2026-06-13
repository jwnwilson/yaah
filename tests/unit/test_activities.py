import tempfile

from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from adapters.runtime.fake import FakeAgentRuntime
from adapters.storage.local import LocalStorageAdapter
from domain.models import Run, RunStage, RunStatus
from interactors.temporal.activities import RunActivities


def _factory():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def _storage():
    return LocalStorageAdapter(base_dir=tempfile.mkdtemp())


def _seed_run(factory) -> str:
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        run = uow.runs.create(Run(owner_id="u1", task_id="t1", team_id="tm1"))
    return run.id


def test_persist_run_state_updates_row():
    factory = _factory()
    run_id = _seed_run(factory)
    acts = RunActivities(factory, FakeAgentRuntime(), _storage())
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
    acts = RunActivities(factory, FakeAgentRuntime(), _storage())
    result = acts.run_stage(
        {
            "run_id": run_id,
            "owner_id": "u1",
            "stage": RunStage.PLAN,
            "task_title": "T",
            "acceptance_criteria": [],
        }
    )
    assert result["outcome"] == "ok"
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        page = uow.run_events.list(filters={"run_id": run_id})
    assert page.total >= 1


def test_cleanup_workspace_deletes_run_dir():
    storage = _storage()
    storage.write_bytes("runs/r1/plan.md", b"data")
    assert storage.exists("runs/r1/plan.md")
    factory = _factory()
    acts = RunActivities(factory, FakeAgentRuntime(), storage)
    acts.cleanup_workspace({"run_id": "r1", "owner_id": "u1"})
    assert not storage.exists("runs/r1")


def test_persist_sets_branch_and_pr_url():
    factory = _factory()
    run_id = _seed_run(factory)
    # T8: constructor is still 3-arg (git/forge added in T9). Use the existing _storage() helper.
    acts = RunActivities(factory, FakeAgentRuntime(), _storage())
    acts.persist_run_state({"run_id": run_id, "owner_id": "u1",
                            "branch": "agent/x", "pr_url": "https://github.com/o/r/pull/1"})
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        run = uow.runs.get(run_id)
    assert run.branch == "agent/x"
    assert run.pr_url == "https://github.com/o/r/pull/1"
