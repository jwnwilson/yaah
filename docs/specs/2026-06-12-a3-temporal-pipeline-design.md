# yaah A3 — Temporal Run Pipeline + FakeAgentRuntime (Design)

**Date:** 2026-06-12
**Status:** Approved design, pending implementation plan
**Phase:** A3 (run-execution spine)
**Depends on:** A1 (control plane), A1.5 (hexrepo refactor), A2 (board UI + run-write endpoints) — all merged to `main`.

## 1. Problem & goal

A2 lets the board create a `pending` run and exposes cancel/approve/reject endpoints, but
nothing executes — the run never advances. A3 adds the **durable execution spine**: each run
becomes a Temporal workflow that drives the §6 pipeline (PLAN → PROVISION → IMPLEMENT →
VERIFY → PR → LEARN), with human gates as Temporal **signals** sent by the existing run-write
endpoints. Agent work is produced by a scripted **`FakeAgentRuntime`** (no real LLM, sandbox,
or GitHub) so the whole loop — staging, gates, retries, crash-resume, status persistence — is
provable without external systems. Real sandbox/GitHub (A4) and the Claude Code runtime +
LiteLLM (A5) slot in later by swapping adapters.

### A3 success criterion

> From the board, start a run on a Ready task and watch it advance stage-by-stage through a
> faked pipeline: it pauses at the plan gate (`gated_all`), resumes on **Approve**, runs
> IMPLEMENT/VERIFY, pauses at the merge gate, and reaches `done` on a second Approve — with
> every stage transition and agent event visible in the run's event feed, all surviving a
> worker restart mid-run. `full_auto` runs straight to `done`; **Reject** ends `failed`;
> **Cancel** ends `cancelled`; a VERIFY that can't pass ends `blocked` in the Attention column.

## 2. Scope

### In scope
- A pure **domain pipeline policy** (stage order, status mapping, gate selection, VERIFY retry).
- **`AgentRuntime`** (event-streaming) and **`WorkspaceProvider`** ports + a scripted
  `FakeAgentRuntime` and a `LocalTempWorkspace`.
- A **Temporal `RunWorkflow`** + activities + worker, consulting the domain policy.
- **API ↔ Temporal** wiring: `start_run` starts the workflow; approve/reject/cancel send
  signals; the workflow is the sole writer of run state.
- A new **`run_events`** append-only table + `GET /runs/{id}/events`.
- **Live local execution**: Temporal dev-server in docker-compose, a worker entrypoint, a
  Temporal client in the API.

### Out of scope (later phases)
- Real sandbox / egress proxy / GitHub App → **PROVISION and PR are stubs** in A3 (A4).
- Real coding agent + LiteLLM → **`FakeAgentRuntime` only**; budgets/cost are faked increments (A5).
- **SSE live streaming** — the board polls `GET /runs/{id}` + `/events` (a later phase adds SSE).
- Real memory writes — **LEARN emits a faked memory-diff event**, writes nothing (A6).
- Cross-model plan review specifics, parallel engineers, janitor/orphan reaping (A4+).

## 3. Decisions log

| Decision | Choice | Rationale |
|---|---|---|
| Pipeline coverage | **All 6 stages, faked** | Proves the whole durable loop; PROVISION/PR/LEARN are stubs |
| Layering | **Pure `domain/pipeline` + Temporal as an adapter** (Approach 1) | Business rules stay I/O-free and unit-testable; A5 swaps the runtime adapter only |
| Runtime port | **Event-streaming** (`run_stage` yields events; final carries `StageResult`) | Mirrors the eventual Claude Code adapter; exercises heartbeat/no-progress paths |
| Fake behavior | **Scripted `FakeAgentRuntime`** (per-stage event lists + outcome) | Deterministic tests for success / fail-then-pass / blocked |
| Progress data | **`run_events` table + polling** | Durable activity feed (spec §4); SSE deferred |
| Status ownership | **Workflow is sole writer; endpoints signal** | No dual-writer drift; matches "workflow is the supervisor" |
| VERIFY exhausted | **→ `blocked`** (Attention column) | First-class blocked; human then cancels/edits — keeps approve/reject = gate-only |
| Runtime infra | **Live: compose Temporal + worker + API client** | Runs execute end-to-end locally; also tested via Temporal's `WorkflowEnvironment` |

## 4. Architecture

```
src/
  domain/
    pipeline.py        # PURE: STAGES order, stage→RunStatus, gates_for(autonomy),
                       # verify policy (max loops), no-progress rule. No I/O / no Temporal.
    runtime.py         # AgentRuntime Protocol + AgentEvent / RunContext / StageResult DTOs
    workspace.py       # WorkspaceProvider Protocol + Workspace DTO
  adapters/
    runtime/fake.py    # FakeAgentRuntime — replays a scripted dict[stage -> events+result]
    workspace/local.py # LocalTempWorkspace — temp dir provision/destroy (no real git in A3)
    database/
      orm.py           # + RunEventRow
      repositories.py  # + RunEventRepository
      uow.py           # + uow.run_events
      ports.py         # + run_events on UnitOfWork Protocol; + RunEvent in Repository set
    temporal/
      workflow.py      # RunWorkflow: deterministic orchestration; consults domain/pipeline
      activities.py    # run_stage_activity (calls AgentRuntime), persist_activity (UoW writes)
      worker.py        # builds client, registers workflow + activities + runtime/workspace
      client.py        # TemporalRunClient: start_run_workflow / signal / (cancel via signal)
      config.py        # address, namespace, task_queue from Settings
  domain/models.py     # + RunEvent DTO; + RunStage enum (or stage constants)
  interactors/
    api/
      routes/runs.py   # start_run starts workflow; approve/reject/cancel -> signals; +events route
      deps.py          # + temporal_client dependency
      settings.py      # + temporal_address, temporal_namespace, task_queue
    worker_main.py     # `python -m interactors.worker_main` -> runs the Temporal worker
tests/
  unit/                # domain/pipeline, FakeAgentRuntime, LocalTempWorkspace, run_event repo
  integration/         # API (workflow start/signals mocked client) + run_events endpoint
  workflow/            # Temporal WorkflowEnvironment tests (time-skipping) with FakeAgentRuntime
```

## 5. Domain pipeline (pure, no I/O)

`domain/pipeline.py`:
- `STAGES = [plan, provision, implement, verify, pr, learn]` (a `RunStage` StrEnum).
- `stage_status(stage) -> RunStatus` → `running` for every active stage (`Run.stage` records
  which); terminal/gate statuses are applied by the workflow, not derived here.
- `gates_for(autonomy) -> set[RunStage]`:
  - `gated_all` → `{plan, pr}`; `gated_merge` → `{pr}`; `full_auto` → `{}`.
- `VERIFY_MAX_LOOPS = 3` (constant; per-project override deferred). `should_retry_verify(loops)`.
- Pure, fully unit-tested; imports no adapters and no Temporal.

`domain/models.py` additions:
- `RunStage` StrEnum (`plan/provision/implement/verify/pr/learn`).
- `RunEvent` DTO: `id, run_id, owner_id, stage, type, message, created_at`.
- `RunEventType` StrEnum: `stage_started, stage_completed, agent_event, gate_opened,
  gate_resolved, blocked, error`.

## 6. Ports & fakes

`domain/runtime.py`:
```python
class AgentEvent(BaseModel):
    type: Literal["progress", "heartbeat", "artifact", "result"]
    stage: RunStage
    message: str = ""
    data: dict = {}

class StageResult(BaseModel):
    outcome: Literal["ok", "fail", "blocked"]
    artifacts: dict = {}
    cost_usd: float = 0.0

class RunContext(BaseModel):
    run_id: str
    stage: RunStage
    task_title: str
    acceptance_criteria: list[str]
    workspace_path: str
    prior_artifacts: dict = {}

class AgentRuntime(Protocol):
    def run_stage(self, ctx: RunContext) -> Iterator[AgentEvent]: ...  # final event.data carries StageResult
    def cancel(self, run_id: str) -> None: ...
```
`adapters/runtime/fake.py` — `FakeAgentRuntime(script: dict[RunStage, list[AgentEvent]] | None)`:
replays the script per stage; default script emits a couple of progress events + an `ok`
`StageResult` for every stage. Tests pass scripts to force `fail` (then-pass on retry) or
`blocked`. Cost is a small fixed increment per stage.

`domain/workspace.py` — `WorkspaceProvider` Protocol: `provision(run_id) -> Workspace`,
`destroy(workspace)`. `adapters/workspace/local.py` — `LocalTempWorkspace` creates/removes a
temp dir (no git in A3).

## 7. Temporal workflow & activities

`adapters/temporal/workflow.py` — `RunWorkflow.run(input: RunInput)` where `RunInput =
{run_id, task_id, owner_id, autonomy, task_title, acceptance_criteria}`:
1. `persist`(status=`running`, stage=`plan`) and a `stage_started` event.
2. For each stage in `STAGES`:
   - call `run_stage_activity` (heartbeating; capped retries; per-stage timeout) → `StageResult`.
   - append `agent_event`/`stage_completed` events; accumulate cost.
   - if `outcome == "blocked"` → `persist`(status=`blocked`) + `blocked` event; **stop**.
   - if stage == `verify` and `outcome == "fail"`: loop back to `implement` while
     `should_retry_verify(loops)`; on exhaustion → `blocked`; **stop**.
   - if stage ∈ `gates_for(autonomy)`: `persist`(status=`awaiting_approval`) + `gate_opened`
     event, then `await workflow.wait_condition(gate signal received)`. On **approve** →
     `gate_resolved` + continue; on **reject** → `failed` + stop.
3. After `learn` → `persist`(status=`done`, stage=`learn`).

**Signals**: `approve()`, `reject()`, `cancel()`. `cancel` at any point → `persist`
(status=`cancelled`) + workspace destroy (stub) + stop. Determinism: every branch decision
comes from `domain/pipeline` (pure) or an activity result; no clock/random in the workflow.

`adapters/temporal/activities.py`:
- `run_stage_activity(ctx)` — resolves the injected `AgentRuntime`, iterates `run_stage`,
  emits a Temporal heartbeat + appends a `run_events` row per event, returns the final
  `StageResult`.
- `persist_activity(run_id, owner_id, *, status?, stage?, cost_usd?, event?)` — the **only**
  DB writer during a run; opens a UoW with `required_filters={"owner_id": owner_id}` (system
  context), updates the run row and/or appends a `run_event`, atomically.

`worker.py` registers `RunWorkflow` + both activities, wiring concrete `FakeAgentRuntime` and
`LocalTempWorkspace`. `client.py` exposes `start_run_workflow(run)` and
`signal(run_id, name)`.

## 8. API ↔ Temporal wiring (refactors A2)

- `POST /work-items/{task_id}/runs` — unchanged validation (task is Ready, project has a team);
  creates `Run(pending)` then `temporal_client.start_run_workflow(...)` (workflow id = run_id).
  If the start call fails, the run is persisted `failed` with an `error` event; returns the run.
- `POST /runs/{id}/approve|reject|cancel` — **refactored**: guard (`approve`/`reject` require
  `status == awaiting_approval`; `cancel` requires non-terminal) → `temporal_client.signal(id,
  name)` → return `202` with the current run. They **no longer write `run.status`**; the
  workflow's `persist_activity` does. `validate_run_transition` stays as the guard's basis.
- `GET /runs/{id}/events` — paginated, owner-scoped list from `run_events`.
- `PATCH /runs/{id}` (metadata) — unchanged.
- `deps.py` adds a `temporal_client` dependency built from Settings; tests inject a fake client.

## 9. Persistence

- `RunEventRow` (`id, run_id, owner_id, stage, type, message, created_at`), `RunEventRepository`,
  `uow.run_events`, and the `UnitOfWork`/`Repository` Protocol additions. Append-only; never updated.
- Owner-scoped like every owned row; activities supply the run's `owner_id` as the required filter.
- `create_all` picks up the new table (alembic still deferred per A1.5).

## 10. Error handling

- Runtime/workspace calls behind ports with typed domain errors; **no silent swallowing**.
- Activity retry policies capped; a stage that ultimately fails → run `failed` + an `error`
  `run_event` carrying the real message.
- Runs **always** reach a terminal state (`done/failed/blocked/cancelled`).
- Worker crash mid-run → Temporal resumes the workflow from history; `persist_activity` is
  idempotent on status (last-writer-wins on the run row; events are append-only).
- Janitor/orphan reaping and hard budget breaches deferred to A4+.

## 11. Testing (80% gate)

- **Domain (pure):** stage order, `stage_status`, `gates_for` per autonomy, `should_retry_verify`.
- **Workflow (`WorkflowEnvironment`, time-skipping):** `full_auto` → `done`; `gated_all` waits
  at plan gate → approve continues → waits at merge gate → approve → `done`; reject → `failed`;
  cancel → `cancelled`; VERIFY fail-then-pass; VERIFY exhausted → `blocked`. Uses
  `FakeAgentRuntime` scripts; activities run against in-memory SQLite UoW.
- **API (integration):** `start_run` invokes the (faked) Temporal client; approve/reject/cancel
  send the correct signal and 409 when not at a gate / terminal; `run_events` owner-scoping.
- **Adapters:** `FakeAgentRuntime` event/outcome scripting; `LocalTempWorkspace` provision/destroy;
  `RunEventRepository`.

## 12. Dev infra

- `docker-compose`: add a **Temporal dev server** service (`temporal server start-dev`,
  lightweight image) exposing `7233` (+ Web UI). Worker started by `make worker`
  (`uv run python -m interactors.worker_main`).
- `pyproject.toml`: add `temporalio`.
- `Settings`: `temporal_address` (default `localhost:7233`), `temporal_namespace`
  (`default`), `task_queue` (`yaah-runs`), env prefix `YAAH_`.
- Update `CLAUDE.md` dev commands + README with the worker/Temporal steps.

## 13. Risks

- **Determinism**: all non-deterministic logic must stay in activities/`domain.pipeline`, never
  the workflow body — enforced by review + the workflow test suite.
- **Test DB across worker threads**: workflow tests run activities against in-memory SQLite —
  reuse the A1.5 `StaticPool`/`check_same_thread` setup; keep activity DB sessions short-lived.
- **A2 endpoint refactor**: changing approve/reject from direct writes to signals updates their
  existing tests; the run-status state machine stays the contract basis.
