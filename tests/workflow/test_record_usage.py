import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.models import (
    AgentRole,
    Project,
    Run,
    WorkItem,
    WorkItemKind,
    WorkItemStatus,
)
from interactors.temporal.activities import RunActivities


@pytest.fixture
def factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _seed(factory):
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        uow.projects.create(Project(id="p1", owner_id="dev-user", name="P", local_path="/tmp/x"))
        uow.work_items.create(WorkItem(id="t1", owner_id="dev-user", project_id="p1",
                                       kind=WorkItemKind.TASK, parent_id="f1", title="T",
                                       status=WorkItemStatus.IN_PROGRESS))
        uow.runs.create(Run(id="r1", owner_id="dev-user", task_id="t1", team_id="tm"))


def test_record_usage_writes_rows_and_recomputes_run_counters(factory):
    _seed(factory)
    acts = RunActivities(factory, runtime=None, storage=None, git=None, forge=None)
    payload = {
        "run_id": "r1", "owner_id": "dev-user", "stage": "implement",
        "agent_role": AgentRole.BACKEND.value,
        "model_usage": {"m1": {"input_tokens": 100, "output_tokens": 20,
                               "cache_read_tokens": 0, "cache_creation_tokens": 0,
                               "cost_usd": 0.5}},
    }
    acts.record_usage(payload)

    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        rows = uow.usage.list(filters={"run_id": "r1"}).results
        run = uow.runs.get("r1")
    assert len(rows) == 1
    assert rows[0].work_item_id == "t1" and rows[0].project_id == "p1"
    assert rows[0].agent_role == AgentRole.BACKEND
    assert run.input_tokens == 100 and run.output_tokens == 20


def test_record_usage_is_idempotent_on_retry(factory):
    _seed(factory)
    acts = RunActivities(factory, runtime=None, storage=None, git=None, forge=None)
    payload = {
        "run_id": "r1", "owner_id": "dev-user", "stage": "implement", "agent_role": None,
        "model_usage": {"m1": {"input_tokens": 100, "output_tokens": 20,
                               "cache_read_tokens": 0, "cache_creation_tokens": 0,
                               "cost_usd": 0.5}},
    }
    acts.record_usage(payload)
    acts.record_usage(payload)  # retry: same dedupe_key

    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        rows = uow.usage.list(filters={"run_id": "r1"}).results
        run = uow.runs.get("r1")
    assert len(rows) == 1               # not duplicated
    assert run.input_tokens == 100      # counter recomputed, not doubled
