import json
import tempfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from temporalio import workflow
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from adapters.storage.local import LocalStorageAdapter
from domain.agent import AgentEvent, StageResult
from domain.models import (
    Project,
    Run,
    WorkItem,
    WorkItemKind,
    WorkItemStatus,
)
from interactors.temporal.activities import RunActivities
from interactors.temporal.workflows import AgentWorkflow


class _StubRuntime:
    """Scripted agent_step: optionally writes an outbox.json, returns a fixed outcome."""

    def __init__(self, outcome="ok", outbox=None, storage=None):
        self._outcome = outcome
        self._outbox = outbox
        self._storage = storage

    def run_stage(self, ctx):
        if self._outbox is not None and self._storage is not None:
            self._storage.write_bytes(
                f"runs/{ctx.run_id}/.orchestration/outbox.json",
                json.dumps(self._outbox).encode(),
            )
        yield AgentEvent(type="result", stage=ctx.stage,
                         data=StageResult(outcome=self._outcome).model_dump())

    def cancel(self, run_id):
        return None


@workflow.defn(name="StubParent")
class StubParent:
    def __init__(self):
        self._reports = []

    @workflow.signal
    def agent_report(self, report: dict) -> None:
        self._reports.append(report)

    @workflow.run
    async def run(self) -> list:
        await workflow.wait_condition(lambda: len(self._reports) >= 1)
        return list(self._reports)


def _factory():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def _seed(factory, owner="u1"):
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": owner})
    with uow.transaction():
        uow.projects.create(Project(id="p1", owner_id=owner, name="P", local_path="/tmp/x"))
        uow.work_items.create(WorkItem(id="t1", owner_id=owner, project_id="p1",
                                       kind=WorkItemKind.TASK, parent_id="f1", title="T",
                                       status=WorkItemStatus.IN_PROGRESS))
        uow.runs.create(Run(id="r1", owner_id=owner, task_id="t1", team_id="tm1"))


def _acts(factory, runtime):
    storage = LocalStorageAdapter(base_dir=tempfile.mkdtemp())
    runtime._storage = runtime._storage or storage
    return RunActivities(factory, runtime, storage, None, None)


def _input(**over):
    base = dict(run_id="r1", owner_id="u1", role="backend", agent_id="a-eng",
                parent_workflow_id="parent-r1", task_title="T", acceptance_criteria=[],
                team_id=None, role_to_agent_id={}, project_id="p1", work_item_id="t1")
    base.update(over)
    return base


def _worker(env, acts, workflows):
    return Worker(env.client, task_queue="t", workflows=workflows,
                  activities=[acts.agent_step, acts.persist_messages, acts.record_event,
                              acts.record_usage],
                  activity_executor=ThreadPoolExecutor(max_workers=4))


@pytest.mark.asyncio
async def test_actor_drains_inbox_then_stops():
    factory = _factory()
    _seed(factory)
    acts = _acts(factory, _StubRuntime(outcome="ok"))
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env, acts, [AgentWorkflow]):
            h = await env.client.start_workflow(AgentWorkflow.run, _input(),
                                                id="agent-r1-backend", task_queue="t")
            await h.signal("deliver", {"body": "do A"})
            await h.signal("deliver", {"body": "do B"})
            await h.signal("stop_now")
            result = await h.result()
    assert result["processed"] == 2


@pytest.mark.asyncio
async def test_actor_routes_outgoing_message_to_peer_and_persists():
    factory = _factory()
    _seed(factory)
    outbox = [{"recipient_kind": "agent", "recipient_role": "qa", "body": "please verify"}]
    acts = _acts(factory, _StubRuntime(outcome="ok", outbox=outbox))
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env, acts, [AgentWorkflow]):
            h = await env.client.start_workflow(
                AgentWorkflow.run, _input(role_to_agent_id={"qa": "a-qa"}),
                id="agent-r1-backend", task_queue="t")
            await h.signal("deliver", {"body": "implement"})
            await h.signal("stop_now")
            await h.result()
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        rows = uow.messages.list(filters={"recipient_agent_id": "a-qa"}).results
    assert len(rows) == 1 and rows[0].body == "please verify"


@pytest.mark.asyncio
async def test_actor_reports_completion_to_parent():
    factory = _factory()
    _seed(factory)
    acts = _acts(factory, _StubRuntime(outcome="ok"))
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env, acts, [AgentWorkflow, StubParent]):
            parent = await env.client.start_workflow(StubParent.run, id="parent-r1",
                                                     task_queue="t")
            h = await env.client.start_workflow(
                AgentWorkflow.run, _input(parent_workflow_id="parent-r1"),
                id="agent-r1-backend", task_queue="t")
            await h.signal("deliver", {"body": "do it"})
            await h.signal("stop_now")
            await h.result()
            reports = await parent.result()
    assert len(reports) == 1 and reports[0]["role"] == "backend"
