# Chat-driven commit → auto-run — Design

**Status:** Design (approved in brainstorming 2026-06-19). Implementation plan to follow via writing-plans.

**Goal:** Let a user converse with the team-lead refinement chat to break work down into epics/features/tasks, then — with a single natural-language "go" — have those drafted items promoted to `Ready`, their parent epics/features activated, and runs auto-started through the existing scheduler/orchestrator. Closes the manual gap between A6a refinement chat (drafts only) and run start.

**Non-goals:** No new run-start machinery (reuse `reconcile_project` + `OrchestratorWorkflow`). No change to autonomy gating of run *stages* (PLAN/PR gates stay as-is). No auto-commit on the same turn a breakdown is first proposed.

## Background — current state

Today the flow is: chat → DRAFT work items (`src/interactors/api/routes/chat.py`) → **human manually promotes to READY** → activate parent → `reconcile_project` starts runs. The refinement agent (`src/domain/refinement.py`) always emits proposals that are persisted as `WorkItemStatus.DRAFT`; it has no way to signal "start these."

Relevant existing pieces this design reuses unchanged:

- `reconcile_project(uow, settings, project_id)` (`src/interactors/scheduling.py`) — finds READY tasks under active epics/features, respects `max_concurrent_runs`, returns run inputs.
- `build_run_and_input` — creates the `Run`, flips task → IN_PROGRESS, builds `run_input` (already includes `autonomy`).
- `activate_item` endpoint (`src/interactors/api/routes/work_items.py`) — the canonical pattern: reconcile inside the txn, then `temporal.start_run_workflow(ri, "OrchestratorWorkflow")` after commit.
- `validate_transition` (`src/domain/transitions/work_items.py`) — already permits `DRAFT → READY`.
- `AutonomyLevel` (`src/domain/projects/projects.py`): `GATED_ALL` / `GATED_MERGE` / `FULL_AUTO`, stored on `Project.autonomy`.

## Decisions (from brainstorming)

1. **One human checkpoint per breakdown** ("confirm in chat, then go") — regardless of autonomy level. The chat is the approval surface; downstream stage gates are unchanged.
2. **Confirmation is natural-language** — the user types "go"/"yes, start it" and the agent classifies it.
3. **Commit signalled by a structured `action` field** on the agent output (Approach A), not keyword sniffing or a second LLM call. Intent is explicit and unit-testable; the commit acts only on already-persisted session items, so a misclassification cannot duplicate work.

## Architecture

Three small additions over the existing A6a surface:

### 1. Agent contract — `action` field

`src/domain/refinement.py` — `RefinementOutput` gains:

```python
class RefinementAction(StrEnum):
    DISCUSS = "discuss"
    COMMIT = "commit"

class RefinementOutput(BaseModel):
    reply: str = ""
    proposals: list[WorkItemProposal] = []
    action: RefinementAction = RefinementAction.DISCUSS
```

System prompt extended so the agent:
- proposes a breakdown as DRAFT (unchanged), and
- **confirms before committing**: after drafting, it ends with "…— confirm and I'll start," and only sets `action: commit` on a *subsequent* affirming user turn. It never commits on the same turn it first proposes.

The Anthropic tool schema (`src/adapters/agent/refinement/anthropic.py`) adds `action` to the `propose` tool. The Fake agent (`src/adapters/agent/refinement/fake.py`) gains deterministic behavior: a message matching an approval token (e.g. starts with "go"/"yes") returns `action: commit` with no new proposals, otherwise `discuss` as today — enough for integration tests without an LLM.

### 2. Provenance — `chat_session_id` on `WorkItem`

So commit knows *exactly* which items to start, every item the chat creates is tagged with its originating session:

- `WorkItem` (`src/domain/projects/work_items.py`): add `chat_session_id: str | None = None`.
- `WorkItemRow` (`adapters/database/orm.py`): nullable `String(32)` column, indexed.
- Alembic migration: add nullable column (upgrade/downgrade).
- The chat endpoint sets `chat_session_id=session.id` when creating items from proposals.

This is the clean, queryable provenance link (and an audit trail), avoiding any guess about "which drafts belong to this conversation."

### 3. Commit path — in the chat endpoint

A pure helper keeps the endpoint thin and the logic unit-testable:

`src/domain/refinement.py` — `select_committable(items)`:
- input: the session's work items;
- returns the TASK items in `DRAFT` (to promote) and the set of parent epic/feature ids that must be activated.
- ignores non-DRAFT items (idempotent: a second "go" finds nothing to start).

`src/interactors/api/routes/chat.py` — when `out.action == COMMIT`, inside the existing transaction:
1. Load DRAFT work items where `chat_session_id == session.id`.
2. For each DRAFT task → `validate_transition(DRAFT, READY)` then update to READY. If an item isn't DRAFT (race/manual edit), skip it and add a note to the reply rather than failing the whole commit.
3. Set `active = True` on parent epics/features (those created in the session and any pre-existing inactive parent of a committed task), mirroring `_set_active` in `work_items.py`, so the scheduler can see the tasks.
4. Call `reconcile_project(uow, settings, project_id)` inside the txn.
5. After the txn commits, launch each returned run input via `temporal.start_run_workflow(ri, "OrchestratorWorkflow")` — identical ordering to `activate_item` (DB first, Temporal after).

The endpoint dependencies grow by `settings` and the Temporal client (both already used elsewhere in the API).

## Data flow

```
user msg ──> POST /projects/{id}/chat
              persist user ChatMessage
              agent.respond(ctx) -> RefinementOutput{reply, proposals, action}
              persist assistant ChatMessage
              create proposals as DRAFT, tagged chat_session_id   (action=discuss OR commit)
   action == commit?
     └─ yes: promote session DRAFT tasks -> READY
             activate parent epics/features
             reconcile_project() -> run_inputs        (inside txn)
             [after commit] start_run_workflow(ri)     -> OrchestratorWorkflow
   return { session_id, reply, created_items, started_runs }
```

## Error handling & edge cases

- **Nothing to start** (commit but no DRAFT tasks: already committed, or only epics/features drafted): no-op the launch; reply says so. Idempotent — items are now READY/IN_PROGRESS, not DRAFT.
- **Concurrency cap:** inherited from `reconcile_project`; tasks beyond `max_concurrent_runs` stay READY and are picked up by `reconcile_project_runs` at run completion.
- **Inactive parent outside the session:** commit activates any inactive parent of a committed task, so "go" reliably starts the task.
- **Invalid transition:** `validate_transition` raises → skip that item, note it in the reply; partial commit is acceptable and visible.
- **Temporal launch failure:** runs launched after the DB commit (same ordering as `activate_item`); items are already READY/IN_PROGRESS so a later reconcile recovers them. No lost work.
- **False-positive commit:** mitigated by the confirm-before-commit prompt rule; worst case starts a breakdown still under discussion — recoverable since every task becomes a reviewable PR and gated autonomy levels keep their PR gate.

## Testing (TDD, 80% gate)

**Domain (unit, pure — `tests/unit/`)**
- `RefinementOutput` parses `action: commit` vs default `discuss`; absent field defaults to `discuss`.
- `select_committable`: returns DRAFT tasks + parent ids to activate; ignores READY/IN_PROGRESS; collects parents needing activation.
- `validate_transition` DRAFT→READY already covered; add a case asserting commit skips non-DRAFT rather than raising.

**Repository/UoW (unit, SQLite in-memory)**
- `chat_session_id` round-trips on `WorkItem`; querying DRAFT items by session is owner-scoped and returns only that session's items.

**API (integration, TestClient — `tests/integration/`)**
- Fake agent returns `commit` → POST `/chat` promotes session tasks to READY, activates parents, and a run is created (assert via runs repo / fake Temporal client capturing `start_run_workflow`).
- `discuss` turn creates DRAFT only and starts nothing (regression guard for A6a behavior).
- Commit with no startable items → 200, no runs launched, reply notes nothing to start.
- Concurrency cap honored: tasks beyond cap stay READY.

**Migration**
- Alembic upgrade/downgrade smoke for the nullable `chat_session_id` column.

The existing `FakeRefinementAgent` and fake Temporal client mean no real LLM or Temporal server is needed in tests.

## Files touched

| Area | File | Change |
|------|------|--------|
| Domain | `src/domain/refinement.py` | `RefinementAction`, `action` on `RefinementOutput`, `select_committable`, prompt update |
| Domain | `src/domain/projects/work_items.py` | `chat_session_id` field |
| Adapter | `src/adapters/database/orm.py` | nullable `chat_session_id` column |
| Adapter | `src/adapters/agent/refinement/anthropic.py` | `action` in tool schema/parse |
| Adapter | `src/adapters/agent/refinement/fake.py` | deterministic commit on approval token |
| Migration | `alembic/versions/*` | add `chat_session_id` |
| API | `src/interactors/api/routes/chat.py` | commit path: promote + activate + reconcile + launch |
| Tests | `tests/unit/*`, `tests/integration/test_chat_api.py` | as above |
