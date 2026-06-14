# AgentWorkflow Actor — Implementation Plan (Plan 3c)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** Add the `AgentWorkflow` Temporal **child-actor**: a durable workflow with a signal-fed mailbox that drains its inbox until empty (calling `agent_step`), routes outgoing messages to peer actors, reports completion to the parent, and uses `continue-as-new` to bound history. **Additive** — does not touch `RunWorkflow` (the parent rewrite is 3d).

**Architecture:** A new `@workflow.defn` class in `src/interactors/temporal/workflows.py`. Signals `deliver`/`stop_now`; queries `queue_depth`/`is_idle`. Drains its `_inbox` calling the Plan-3b `agent_step` activity; persists + routes each outgoing `OutboundMessage` (peer → `deliver` signal to `agent-{run_id}-{role}`; persist via `persist_messages`); signals the parent `agent_report` when a brief completes. Registered in the worker.

**Tech Stack:** Python 3.12, Temporal (`temporalio`), pytest + `WorkflowEnvironment.start_time_skipping` (see `tests/workflow/test_run_workflow.py` for the exact harness).

**Scope:** Plan 3c of the lead-orchestration foundation (ADR-0002 / `docs/specs/2026-06-14-lead-orchestration-design.md`). Builds on Plans 1-2 (domain) and 3a-3b (RunContext.instructions, activities). **Deferred to 3d:** the `RunWorkflow` parent rewrite (orchestrator loop, quiescence, guards, monitor, gates) + multi-wave e2e. In 3c the parent is represented in tests by a tiny stub workflow that records `agent_report` signals.

## Determinism rules (Temporal — follow exactly)
- No wall-clock/random; all waiting via `workflow.wait_condition`. Mutating signal state only in signal handlers. Activities for all I/O. `continue_as_new` only when the inbox is empty and not stopping.

## Workflow-id convention
Each actor: `agent-{run_id}-{role}` (role = `AgentRole` value). The parent passes `parent_workflow_id` and `role_to_agent_id` in the actor input.

## File Structure
| File | Responsibility | Change |
|---|---|---|
| `src/interactors/temporal/workflows.py` | `AgentWorkflow` class | Modify (append) |
| `src/interactors/temporal/worker.py` | register `AgentWorkflow` | Modify |
| `tests/workflow/test_agent_workflow.py` | actor behavior in the test env | Create |

---

## Task 1: `AgentWorkflow` skeleton — signals, queries, drain loop

**Files:** Modify `src/interactors/temporal/workflows.py`; Create `tests/workflow/test_agent_workflow.py`.

- [ ] Step 1: Write the failing test (mirror `tests/workflow/test_run_workflow.py`: `WorkflowEnvironment.start_time_skipping`, a `Worker` registering `AgentWorkflow` + a real `RunActivities` built with a **stub runtime** whose `agent_step` is exercised). Use a stub runtime that writes nothing and returns an `ok` result so `agent_step` reports `completed_brief=True`. Start the actor, send two `deliver` signals, then `stop_now`, and assert the workflow result reports `processed == 2`.

Test skeleton:
```python
import tempfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from adapters.agent.runtime.fake import FakeAgentRuntime
from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.storage.local import LocalStorageAdapter
from interactors.temporal.activities import RunActivities
from interactors.temporal.workflows import AgentWorkflow


def _factory():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def _acts(factory):
    storage = LocalStorageAdapter(base_dir=tempfile.mkdtemp())
    return RunActivities(factory, FakeAgentRuntime(storage=storage), storage, None, None)


def _input(**over):
    base = dict(run_id="r1", owner_id="u1", role="backend", agent_id="a-eng",
                parent_workflow_id="parent-r1", task_title="T", acceptance_criteria=[],
                team_id=None, role_to_agent_id={}, project_id=None, work_item_id=None)
    base.update(over)
    return base


@pytest.mark.asyncio
async def test_actor_drains_inbox_then_stops():
    factory = _factory()
    acts = _acts(factory)
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue="t",
                          workflows=[AgentWorkflow],
                          activities=[acts.agent_step, acts.persist_messages, acts.record_event,
                                      acts.record_usage],
                          activity_executor=ThreadPoolExecutor(max_workers=4)):
            h = await env.client.start_workflow(AgentWorkflow.run, _input(),
                                                id="agent-r1-backend", task_queue="t")
            await h.signal("deliver", {"body": "do A"})
            await h.signal("deliver", {"body": "do B"})
            await h.signal("stop_now")
            result = await h.result()
    assert result["processed"] == 2
```

- [ ] Step 2: Run -> FAIL (`cannot import name 'AgentWorkflow'`). `uv run pytest tests/workflow/test_agent_workflow.py -v`

- [ ] Step 3: Implement the class in `workflows.py` (append; reuse the `_STAGE_TIMEOUT`/`_RETRY` constants already defined in that module):
```python
_HISTORY_LIMIT = 4000


@workflow.defn(name="AgentWorkflow")
class AgentWorkflow:
    def __init__(self) -> None:
        self._inbox: list[dict] = []
        self._idle = False
        self._stop = False

    @workflow.signal
    def deliver(self, msg: dict) -> None:
        self._inbox.append(msg)
        self._idle = False

    @workflow.signal
    def stop_now(self) -> None:
        self._stop = True

    @workflow.query
    def queue_depth(self) -> int:
        return len(self._inbox)

    @workflow.query
    def is_idle(self) -> bool:
        return self._idle

    @workflow.run
    async def run(self, inp: dict) -> dict:
        run_id, owner_id, role = inp["run_id"], inp["owner_id"], inp["role"]
        processed = 0
        while not self._stop:
            await workflow.wait_condition(lambda: bool(self._inbox) or self._stop)
            while self._inbox and not self._stop:
                msg = self._inbox.pop(0)
                result = await workflow.execute_activity(
                    "agent_step",
                    {"run_id": run_id, "owner_id": owner_id, "role": role,
                     "incoming": msg.get("body", ""), "task_title": inp["task_title"],
                     "acceptance_criteria": inp.get("acceptance_criteria", []),
                     "team_id": inp.get("team_id")},
                    start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)
                processed += 1
                await self._route_outgoing(inp, result.get("outgoing", []))
                if result.get("completed_brief"):
                    await self._report(inp, result.get("outcome", "ok"))
            self._idle = True
            if (workflow.info().get_current_history_length() > _HISTORY_LIMIT
                    and not self._inbox and not self._stop):
                workflow.continue_as_new(inp)
        return {"role": role, "processed": processed}

    async def _route_outgoing(self, inp: dict, outgoing: list[dict]) -> None:
        if not outgoing:
            return
        messages = []
        for out in outgoing:
            recipient_role = out.get("recipient_role")
            recipient_agent_id = (
                inp["role_to_agent_id"].get(recipient_role)
                if out.get("recipient_kind") == "agent" else None
            )
            messages.append({
                "owner_id": inp["owner_id"], "sender_kind": "agent",
                "sender_agent_id": inp["agent_id"], "recipient_kind": out["recipient_kind"],
                "recipient_agent_id": recipient_agent_id, "kind": out.get("kind", "chat"),
                "subject": out.get("subject", ""), "body": out["body"],
                "run_id": inp["run_id"], "work_item_id": inp.get("work_item_id"),
                "project_id": inp.get("project_id"),
            })
            if out.get("recipient_kind") == "agent" and recipient_role:
                peer_id = f"agent-{inp['run_id']}-{recipient_role}"
                if peer_id != workflow.info().workflow_id:
                    await workflow.get_external_workflow_handle(peer_id).signal(
                        "deliver", {"body": out["body"]})
        await workflow.execute_activity(
            "persist_messages", {"owner_id": inp["owner_id"], "messages": messages},
            start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)

    async def _report(self, inp: dict, outcome: str) -> None:
        await workflow.get_external_workflow_handle(inp["parent_workflow_id"]).signal(
            "agent_report", {"role": inp["role"], "outcome": outcome})
```
Note: the `_report`/peer signals target workflow ids that may not exist in the Task-1 test (parent `parent-r1` is not running). To keep Task 1 hermetic, the Task-1 test's stub runtime should return `completed_brief=False` (outcome `ok` but no report) and emit no outgoing, so neither external signal fires. Add a `FakeAgentRuntime` script or a stub that yields a `result` event with `outcome="ok"` only. If signaling a missing workflow raises, guard `_report`/peer-signal calls in a try/except that records (does not fail the actor) — implementer's choice, documented.

- [ ] Step 4: Run -> PASS.
- [ ] Step 5: Commit `feat: AgentWorkflow actor with signal mailbox and drain loop`.

---

## Task 2: peer routing + parent report (two-actor + stub-parent tests)

**Files:** Modify `tests/workflow/test_agent_workflow.py`; register `AgentWorkflow` in `worker.py`.

- [ ] Step 1: Add two tests:
  (a) **peer delivery** — run two actors (`agent-r1-backend`, `agent-r1-qa`); the backend's `agent_step` (via a stub runtime that writes an `outbox.json` addressed to role `qa`) emits one outbound; assert the qa actor's `queue_depth` query becomes >0 (it received a `deliver`) or that a `Message` row to the qa agent was persisted.
  (b) **parent report** — define a tiny stub `@workflow.defn` parent that has an `agent_report` signal recording into a list queryable via a `reports()` query; run it + one actor whose brief completes; assert the parent recorded one report.
- [ ] Step 2: Run -> FAIL. Step 3: ensure routing/report code paths work; register `AgentWorkflow` in `worker.run_worker`'s `workflows=[...]`. Step 4: Run -> PASS.
- [ ] Step 5: Commit `feat: peer routing + parent report for AgentWorkflow`.

---

## Task 3: Gate & PR
- [ ] `make coverage` (>=80%), `make lint` (clean), full `uv run pytest -q` to confirm no regression (existing `tests/workflow/test_run_workflow.py` still green).
- [ ] Push, open PR `feat: AgentWorkflow actor (orchestration foundation, PR3c)`; body: the actor (mailbox/drain/route/report/continue-as-new), additive (RunWorkflow untouched), 3d (parent rewrite + e2e) deferred.

---

## Self-Review
- Actor: signals (deliver/stop_now), queries (queue_depth/is_idle), drain-until-empty loop calling `agent_step`, outgoing routing (peer `deliver` + `persist_messages`), parent `agent_report`, `continue_as_new` on history growth → Tasks 1-2. Matches spec section 5 "Child AgentWorkflow".
- Determinism: only signals mutate state; all waits via `wait_condition`; I/O via activities; `continue_as_new` guarded on empty inbox.
- Additive: `RunWorkflow` untouched; registered alongside it. Deferred: 3d parent rewrite + e2e (where this actor is spawned for real and quiescence/guards/monitor/gates are wired).
- Test approach pinned to the existing `WorkflowEnvironment.start_time_skipping` harness; parent represented by a stub workflow in tests.
