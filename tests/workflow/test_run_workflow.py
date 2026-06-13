import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from adapters.runtime.fake import FakeAgentRuntime
from interactors.temporal.activities import RunActivities
from interactors.temporal.workflows import RunWorkflow
from domain.models import AutonomyLevel, Run, RunStage, RunStatus
from domain.runtime import AgentEvent, StageResult


def _factory():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def _seed(factory, owner="u1") -> str:
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": owner})
    with uow.transaction():
        run = uow.runs.create(Run(owner_id=owner, task_id="t1", team_id="tm1"))
    return run.id


def _run_status(factory, run_id, owner="u1"):
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": owner})
    with uow.transaction():
        return uow.runs.get(run_id).status


def _input(run_id, autonomy):
    return {
        "run_id": run_id,
        "owner_id": "u1",
        "task_id": "t1",
        "autonomy": autonomy,
        "task_title": "T",
        "acceptance_criteria": [],
    }


async def _worker(env, factory, runtime):
    acts = RunActivities(factory, runtime)
    return Worker(
        env.client,
        task_queue="test-q",
        workflows=[RunWorkflow],
        activities=[acts.persist_run_state, acts.record_event, acts.run_stage],
        activity_executor=ThreadPoolExecutor(max_workers=4),
    )


@pytest.mark.asyncio
async def test_full_auto_runs_to_done():
    factory = _factory()
    run_id = _seed(factory)
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with await _worker(env, factory, FakeAgentRuntime()):
            await env.client.execute_workflow(
                RunWorkflow.run,
                _input(run_id, AutonomyLevel.FULL_AUTO),
                id=run_id,
                task_queue="test-q",
            )
    assert _run_status(factory, run_id) == RunStatus.DONE


@pytest.mark.asyncio
async def test_gated_all_waits_then_approves_to_done():
    factory = _factory()
    run_id = _seed(factory)
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with await _worker(env, factory, FakeAgentRuntime()):
            handle = await env.client.start_workflow(
                RunWorkflow.run,
                _input(run_id, AutonomyLevel.GATED_ALL),
                id=run_id,
                task_queue="test-q",
            )
            wh = env.client.get_workflow_handle(run_id)

            # Disable time-skipping while we poll+signal so activities are not
            # killed by the test server advancing past their schedule timeout.
            async def _poll_and_approve():
                # Wait until workflow reaches AWAITING_APPROVAL, then signal.
                for _ in range(200):
                    await asyncio.sleep(0.05)
                    status = _run_status(factory, run_id)
                    if status == RunStatus.AWAITING_APPROVAL:
                        await wh.signal("approve")
                        break

            with env.auto_time_skipping_disabled():
                # First gate (PLAN)
                await _poll_and_approve()
                # Second gate (PR): poll again after the workflow resumes
                await _poll_and_approve()

            await handle.result()
    assert _run_status(factory, run_id) == RunStatus.DONE


@pytest.mark.asyncio
async def test_reject_ends_failed():
    factory = _factory()
    run_id = _seed(factory)
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with await _worker(env, factory, FakeAgentRuntime()):
            handle = await env.client.start_workflow(
                RunWorkflow.run,
                _input(run_id, AutonomyLevel.GATED_ALL),
                id=run_id,
                task_queue="test-q",
            )
            await env.client.get_workflow_handle(run_id).signal("reject")
            await handle.result()
    assert _run_status(factory, run_id) == RunStatus.FAILED


@pytest.mark.asyncio
async def test_verify_exhausted_blocks():
    factory = _factory()
    run_id = _seed(factory)
    script = {
        RunStage.VERIFY: [
            AgentEvent(
                type="result",
                stage=RunStage.VERIFY,
                data=StageResult(outcome="fail").model_dump(),
            )
        ]
    }
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with await _worker(env, factory, FakeAgentRuntime(script=script)):
            await env.client.execute_workflow(
                RunWorkflow.run,
                _input(run_id, AutonomyLevel.FULL_AUTO),
                id=run_id,
                task_queue="test-q",
            )
    assert _run_status(factory, run_id) == RunStatus.BLOCKED
