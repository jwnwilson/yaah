# Orchestration Activities — Implementation Plan (Plan 3b)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add the four Temporal activities the orchestrator needs — `persist_messages`, `invoke_lead`, `agent_step`, `run_monitor` — using a **file-based lead-decision transport**: the agent writes a JSON artifact to the workspace and the activity reads + validates it with Plan 2's parsers.

**Architecture:** New methods on `RunActivities` (`src/interactors/temporal/activities.py`), reusing the existing `run_stage` pattern (select agent by role -> build manifest -> build `RunContext` -> consume runtime events -> record events/usage). The runtime is driven with `RunContext.instructions` (Plan 3a). Decisions/verdicts/outgoing-messages are exchanged as JSON files under `runs/{run_id}/.orchestration/`. Registered in the worker. **Additive** — the existing `run_stage` and `RunWorkflow` are untouched (the workflow rewrite is Plan 3d).

**Tech Stack:** Python 3.12, Temporal activities, Pydantic v2, pytest (SQLite in-memory + a stub runtime).

**Scope:** Plan 3b of the lead-orchestration foundation (ADR-0002 / `docs/specs/2026-06-14-lead-orchestration-design.md`). Builds on Plan 1 (`Message`/repo), Plan 2 (`domain/orchestration.py`, `orchestration_prompts.py`), Plan 3a (`RunContext.instructions`, event types). **Deferred:** the `AgentWorkflow` actor (3c) and the `RunWorkflow` parent rewrite + e2e (3d).

## File conventions (the transport)
All under the run workspace `runs/{run_id}/.orchestration/`:
- `decision.json` — the lead's `OrchestrationDecision` (written by `invoke_lead`'s agent, read by the activity).
- `outbox.json` — optional list of `OutboundMessage` dicts a worker wants sent (read by `agent_step`).
- `verdict.json` — the monitor's `MonitorVerdict` (read by `run_monitor`).
Activities read via `self._storage.read_text(key)` / `self._storage.exists(key)`; the agent is instructed (in its prompt) to write the file.

## File Structure
| File | Responsibility | Change |
|---|---|---|
| `src/interactors/temporal/activities.py` | 4 new activities + a `_run_instructed_agent` helper | Modify |
| `src/interactors/temporal/worker.py` | register the 4 activities | Modify |
| `tests/unit/test_orchestration_activities.py` | activity unit tests (SQLite + stub runtime) | Create |

---

## Task 1: `persist_messages` activity (pure DB; start here)

**Files:** Modify `src/interactors/temporal/activities.py`; Test `tests/unit/test_orchestration_activities.py`.

`persist_messages(payload)` writes a list of `Message` dicts to the owner-scoped repo. Idempotent on `id` (skip if it already exists). Used by the actor/workflow to record delivered + outgoing messages.

- [ ] Step 1: Write the failing test
```python
# tests/unit/test_orchestration_activities.py
from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.models import MessageKind, MessageRecipientKind, MessageSenderKind


def _factory():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def _acts(factory, runtime=None):
    # build a minimal RunActivities; only the session_factory + runtime are exercised here
    from interactors.temporal.activities import RunActivities
    return RunActivities(factory, runtime, storage=None, git=None, forge=None)


def _msg_dict():
    return dict(
        owner_id="dev-user", sender_kind=MessageSenderKind.AGENT, sender_agent_id="a-lead",
        recipient_kind=MessageRecipientKind.AGENT, recipient_agent_id="a-eng",
        kind=MessageKind.DISPATCH, body="go", run_id="r1",
    )


def test_persist_messages_writes_rows():
    factory = _factory()
    acts = _acts(factory)
    acts.persist_messages({"owner_id": "dev-user", "messages": [_msg_dict()]})
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        assert uow.messages.list().total == 1


def test_persist_messages_is_idempotent_on_id():
    factory = _factory()
    acts = _acts(factory)
    from domain.models import Message
    m = Message(**_msg_dict())
    acts.persist_messages({"owner_id": "dev-user", "messages": [m.model_dump(mode="json")]})
    acts.persist_messages({"owner_id": "dev-user", "messages": [m.model_dump(mode="json")]})
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        assert uow.messages.list().total == 1
```

- [ ] Step 2: Run -> FAIL (`RunActivities` has no `persist_messages`). `uv run pytest tests/unit/test_orchestration_activities.py -k persist -v`

- [ ] Step 3: Implement. Add to `RunActivities` (note: `@activity.defn`, follows the `record_event` pattern which uses `self._uow`):
```python
    @activity.defn(name="persist_messages")
    def persist_messages(self, payload: dict) -> None:
        from domain.models import Message
        owner_id = payload["owner_id"]
        uow = self._uow(owner_id)
        with uow.transaction():
            for raw in payload.get("messages", []):
                msg = Message(**raw)
                try:
                    uow.messages.get(msg.id)
                    continue  # already persisted
                except Exception:  # noqa: BLE001 - not found -> create
                    uow.messages.create(msg)
```

- [ ] Step 4: Run -> PASS.
- [ ] Step 5: Commit `feat: persist_messages activity`.

---

## Task 2: `_run_instructed_agent` helper

**Files:** Modify `src/interactors/temporal/activities.py`.

Extract the reusable "run one agent with a brief" core, modeled on `run_stage` (which already does: select agent by role via `capabilities.select_agent`, assemble manifest with skills/mcps/secrets, audit, build `RunContext`, iterate `self._runtime.run_stage(ctx)` recording events + usage, `result_of(events)`). The helper differs from `run_stage` only by taking an explicit `role` + `instructions` and a stage label.

- [ ] Step 1: Write the failing test (uses a stub runtime that records the ctx it received)
```python
def test_run_instructed_agent_passes_instructions_and_returns_result():
    from domain.models import RunStage
    from domain.runtime import AgentEvent, StageResult

    class StubRuntime:
        def __init__(self): self.ctx = None
        def run_stage(self, ctx):
            self.ctx = ctx
            yield AgentEvent(type="result", stage=ctx.stage,
                             data=StageResult(outcome="ok", cost_usd=0.1).model_dump())
        def cancel(self, run_id): ...

    factory = _factory()
    rt = StubRuntime()
    acts = _acts(factory, runtime=rt)
    result = acts._run_instructed_agent(
        {"run_id": "r1", "owner_id": "dev-user", "task_title": "t",
         "acceptance_criteria": ["c"], "team_id": None},
        role=None, instructions="BRIEF", stage=RunStage.IMPLEMENT,
    )
    assert rt.ctx.instructions == "BRIEF"
    assert result.outcome == "ok"
```
(Note: pass `storage` so `local_path` works; if `storage=None`, have the helper fall back to a temp path. The implementer should construct `_acts` with a `LocalStorageAdapter(base_dir=tmp_path)` if `local_path` is needed — adjust the `_acts` helper accordingly.)

- [ ] Step 2: Run -> FAIL.
- [ ] Step 3: Implement `_run_instructed_agent(self, payload, *, role, instructions, stage) -> StageResult` by adapting `run_stage`'s body: build the manifest for `role` (reuse the same skills/mcps/secrets assembly as `run_stage`; when `role is None` or no team, `agent_manifest=None`), build `RunContext(run_id, stage, task_title, acceptance_criteria, workspace_path=self._storage.local_path(f"runs/{run_id}"), instructions=instructions, agent=agent_manifest)`, consume the runtime recording events (`RunEventType.AGENT_EVENT`) + usage exactly as `run_stage` does, and return `result_of(events)`. Keep `run_stage` itself unchanged.
- [ ] Step 4: Run -> PASS.
- [ ] Step 5: Commit `feat: _run_instructed_agent helper`.

---

## Task 3: `invoke_lead` activity (file-based decision transport)

**Files:** Modify `activities.py`; Test append.

`invoke_lead(payload)`: build the orchestrator prompt with `orchestration_prompts.build_orchestrator_prompt(...)` (from `OrchestrationState` rehydrated from `payload["state"]`, available roles from the team), append a line instructing the agent to write its decision JSON to `.orchestration/decision.json`, run the LEAD agent via `_run_instructed_agent`, then read+parse the file with `parse_decision`. Bounded retry (default 2) re-running with an error hint; on exhaustion return `{"intent": "block", "rationale": "lead did not produce a valid decision"}`. Return `{"decision": <dict>, "cost_usd": <float>}`.

- [ ] Step 1: Test with a stub runtime whose `run_stage` writes a valid `decision.json` into the workspace, asserting `invoke_lead` returns a parsed `continue` decision with the dispatch. (Use `LocalStorageAdapter(base_dir=tmp_path)`; the stub writes `f"runs/{ctx.run_id}/.orchestration/decision.json"` via the storage adapter.)
- [ ] Step 2: Run -> FAIL.
- [ ] Step 3: Implement per the description. Read with `self._storage.read_text(f"runs/{run_id}/.orchestration/decision.json")` guarded by `self._storage.exists(...)`; `parse_decision(json.loads(text))`; catch `OrchestrationContractError` / `json` errors for the retry loop; record an `AGENT_DISPATCHED` event per dispatch via `record_event`.
- [ ] Step 4: Run -> PASS.
- [ ] Step 5: Commit `feat: invoke_lead activity with file-based decision transport`.

---

## Task 4: `agent_step` activity

**Files:** Modify `activities.py`; Test append.

`agent_step(payload)`: run the worker for `payload["role"]` with `instructions = payload["incoming"]` (the dispatch/message body) via `_run_instructed_agent`; after the run, read optional `.orchestration/outbox.json` (list of `OutboundMessage` dicts) and map the `StageResult.outcome` to `AgentOutcome`; return `AgentStepResult(outcome=..., completed_brief=(outcome=="ok"), outgoing=[...], artifacts=result.artifacts, cost_usd=result.cost_usd).model_dump()`. Record an `AGENT_REPORTED` event.

- [ ] Step 1: Test with a stub runtime that writes an `outbox.json` with one peer message and returns outcome ok; assert the returned `AgentStepResult` has `completed_brief=True` and one outgoing message.
- [ ] Step 2: Run -> FAIL. Step 3: Implement. Step 4: PASS. Step 5: Commit `feat: agent_step activity`.

---

## Task 5: `run_monitor` activity + worker registration

**Files:** Modify `activities.py`, `worker.py`; Test append.

`run_monitor(payload)`: run the QA/checker (`role` from payload, default QA) with instructions to verify the acceptance criteria and write `.orchestration/verdict.json`; read+`parse_verdict`; on missing/invalid return `MonitorVerdict(complete=False, notes="monitor produced no verdict")`. Record `MONITOR_STARTED` + `MONITOR_VERDICT` events. Return the verdict dict.

Then register all four in `worker.build_activities`'s returned list:
`acts.persist_messages, acts.invoke_lead, acts.agent_step, acts.run_monitor`.

- [ ] Step 1: Test `run_monitor` with a stub runtime writing a `verdict.json` (complete=true). Step 2: FAIL. Step 3: Implement + register. Step 4: PASS (`uv run pytest tests/unit/test_orchestration_activities.py -v`). Step 5: Commit `feat: run_monitor activity + register orchestration activities`.

---

## Task 6: Gate & PR
- [ ] `make coverage` (>=80%), `make lint` (clean).
- [ ] Push, open PR: title `feat: orchestration activities (orchestration foundation, PR3b)`; body summarizing the four activities + file-based transport, noting actor (3c) and workflow rewrite (3d) are deferred and the existing pipeline is untouched.

---

## Self-Review
- Activities: persist_messages (T1), invoke_lead (T3), agent_step (T4), run_monitor (T5) + shared helper (T2) + registration (T5). Covers spec section 5 "three activity contracts" + message persistence.
- Transport: file-based JSON under `runs/{id}/.orchestration/`, validated with Plan 2's `parse_decision`/`parse_verdict`; bounded retry on the lead. Matches the spec's "constrained ... or final-JSON contract; bounded retry on schema miss".
- Additive: `run_stage` and `RunWorkflow` untouched; no regression. Deferred: 3c actor, 3d parent rewrite + e2e.
- Placeholder note: Tasks 3-5 specify contracts + the `run_stage` template to follow rather than full line-by-line code, because these activities closely mirror the existing `run_stage` body (select agent -> manifest -> RunContext -> consume runtime -> record events/usage); the implementer adapts that proven code with the documented differences (instructions + file read). All signatures, file keys, return shapes, and event types are pinned.
