import asyncio
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from adapters.git.fake import FakeGit, FakeGitForge
from adapters.storage.local import LocalStorageAdapter
from domain.models import (
    AutonomyLevel,
    Project,
    Run,
    RunStatus,
    WorkItem,
    WorkItemKind,
    WorkItemStatus,
)
from domain.runtime import AgentEvent, StageResult
from interactors.temporal.activities import RunActivities
from interactors.temporal.workflows import AgentWorkflow, OrchestratorWorkflow


def _default_lead(instr):
    return ({"intent": "continue",
             "dispatches": [{"target_role": "backend", "instructions": "build"}]}
            if "wave 0" in instr else {"intent": "verify"})


def _block_lead(instr):
    return {"intent": "block", "rationale": "infeasible"}


class _ScriptRuntime:
    """Lead decision via `lead` callable; monitor writes a complete verdict; workers ok."""

    def __init__(self, storage=None, lead=_default_lead):
        self._storage = storage
        self._lead = lead

    def run_stage(self, ctx):
        instr = ctx.instructions or ""
        if "decision.json" in instr:
            self._storage.write_bytes(
                f"runs/{ctx.run_id}/.orchestration/decision.json",
                json.dumps(self._lead(instr)).encode())
        elif "verdict.json" in instr:
            self._storage.write_bytes(
                f"runs/{ctx.run_id}/.orchestration/verdict.json",
                json.dumps({"complete": True}).encode())
        yield AgentEvent(type="result", stage=ctx.stage,
                         data=StageResult(outcome="ok").model_dump())

    def cancel(self, run_id):
        return None


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


def _status(factory, owner="u1"):
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": owner})
    with uow.transaction():
        return uow.runs.get("r1").status


def _worker(env, factory, lead=_default_lead):
    storage = LocalStorageAdapter(base_dir=tempfile.mkdtemp())
    acts = RunActivities(factory, _ScriptRuntime(storage, lead), storage,
                         FakeGit(), FakeGitForge())
    return Worker(
        env.client, task_queue="t",
        workflows=[OrchestratorWorkflow, AgentWorkflow],
        activities=[acts.provision_workspace, acts.invoke_lead, acts.agent_step,
                    acts.run_monitor, acts.persist_messages, acts.persist_run_state,
                    acts.record_event, acts.record_usage, acts.open_pr,
                    acts.capture_memory, acts.cleanup_workspace],
        activity_executor=ThreadPoolExecutor(max_workers=4))


def _input(autonomy):
    return {"run_id": "r1", "owner_id": "u1", "task_id": "t1", "project_id": "p1",
            "autonomy": autonomy, "task_title": "T", "acceptance_criteria": ["works"],
            "body": "", "profile": "remote", "repo_ref": "x", "base": "main",
            "team_id": None, "available_roles": ["backend", "qa"],
            "role_to_agent_id": {"lead": "a-lead", "backend": "a-eng", "qa": "a-qa"}}


@pytest.mark.asyncio
async def test_orchestrator_multiwave_runs_to_done():
    factory = _factory()
    _seed(factory)
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env, factory):
            await env.client.execute_workflow(
                OrchestratorWorkflow.run, _input(AutonomyLevel.FULL_AUTO),
                id="r1", task_queue="t")
    assert _status(factory) == RunStatus.DONE


@pytest.mark.asyncio
async def test_orchestrator_blocks_when_lead_blocks():
    factory = _factory()
    _seed(factory)
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env, factory, lead=_block_lead):
            await env.client.execute_workflow(
                OrchestratorWorkflow.run, _input(AutonomyLevel.FULL_AUTO),
                id="r1", task_queue="t")
    assert _status(factory) == RunStatus.BLOCKED


@pytest.mark.asyncio
async def test_orchestrator_gated_pr_waits_then_approves():
    factory = _factory()
    _seed(factory)
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env, factory):
            handle = await env.client.start_workflow(
                OrchestratorWorkflow.run, _input(AutonomyLevel.GATED_MERGE),
                id="r1", task_queue="t")

            async def _approve():
                for _ in range(200):
                    await asyncio.sleep(0.05)
                    if _status(factory) == RunStatus.AWAITING_APPROVAL:
                        await env.client.get_workflow_handle("r1").signal("approve")
                        return

            with env.auto_time_skipping_disabled():
                await _approve()
            await handle.result()
    assert _status(factory) == RunStatus.DONE


@pytest.mark.asyncio
async def test_orchestrator_persists_lead_dispatch_message():
    factory = _factory()
    _seed(factory)
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env, factory):
            await env.client.execute_workflow(
                OrchestratorWorkflow.run, _input(AutonomyLevel.FULL_AUTO),
                id="r1", task_queue="t")
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        dispatched = uow.messages.list(filters={"kind": "dispatch"}).results
    assert any(
        m.sender_agent_id == "a-lead" and m.recipient_agent_id == "a-eng"
        for m in dispatched
    ), "lead's dispatch should be persisted as a Message for the inbox"
