# yaah A5d — Token / Usage Tracking (Design)

**Date:** 2026-06-13
**Status:** Approved design, pending implementation plan
**Phase:** A5d (usage observability — foundation for phase C budget UIs)
**Depends on:** A3 (Temporal pipeline + `run_events`), A5ab (Claude Code runtime + `stream_json`), A5c (agent capability/role selection) — all merged or in flight on `main`.

## 1. Problem & goal

Runs already cost real money the moment the Claude Code runtime lands, but yaah captures
almost none of it. The runtime's `result` event carries a full `usage` block
(`input_tokens`, `output_tokens`, `cache_read_input_tokens`,
`cache_creation_input_tokens`) and a per-model `modelUsage` map; `stream_json.parse`
reads only `total_cost_usd` and discards the rest. `Run.cost_usd` is a single rolled-up
float with no token detail, no per-stage/per-agent/per-model breakdown, and no way to
answer the core question **"what did building this feature cost?"**

A5d makes token usage a first-class, queryable fact: capture full token + cost detail per
stage execution per model, persist it append-only, and expose owner-scoped rollups across
the work-item hierarchy (task → feature → epic → project) and by stage, agent role, and
model. It is the data foundation phase C's budget UIs and Spec A5e's budget-threshold
notifications will consume — but **A5d does no budget enforcement**.

### A5d success criterion

> Run a feature's task end-to-end through the pipeline, then `GET
> /work-items/{feature_id}/usage` and see total input/output/cache tokens and cost for the
> feature, broken down by stage, by agent role, and by model — with the same totals
> reconciling against the per-run `GET /runs/{id}/usage` and the project rollup. Numbers
> survive a worker restart mid-run (append-only rows; idempotent counters).

## 2. Scope

### In scope
- Extend `stream_json.parse` to capture the `result` event's `usage` + `modelUsage`.
- A pure **`TokenUsage`** value object (`domain/usage.py`) with immutable aggregation +
  rollup/group-by helpers.
- `StageResult.usage` carrying structured token detail (cost mirrored for back-compat).
- An append-only **`UsageRecord`** table (one row per stage-execution per model), repository,
  UoW property, and Protocol entries.
- A **`record_usage`** Temporal activity (the run's only usage writer) + token counters on
  `Run`, written atomically alongside existing state.
- Owner-scoped **read API**: `GET /runs/{id}/usage`, `GET /work-items/{id}/usage`,
  `GET /projects/{id}/usage`, each with optional `group_by` and (project) time window.

### Out of scope (later phases)
- **Budget enforcement** — no caps, no run pausing/blocking on spend. Schema and read
  service are designed so a future check can consume "current spend"; that's all (phase C).
- **Budget-threshold notifications** — the trigger lives in A5e; A5d only exposes spend.
- **Cost dashboards / charts** — the board UI usage panels are a thin follow-up; A5d ships
  the API. (A minimal per-run usage view in the run drawer is the only UI touched.)
- **Cross-currency / pricing tables** — cost comes straight from the runtime's
  `total_cost_usd` / `modelUsage` cost; yaah does not compute price from tokens.
- **Retention/rollup compaction** — append-only forever for now; pruning deferred.

## 3. Decisions log

| Decision | Choice | Rationale |
|---|---|---|
| Rollup strategy | **On-read SQL aggregation** over append-only rows | Always correct, no drift, trivial at current scale; avoids materialized-counter write complexity (KISS/YAGNI) |
| Row granularity | **One `UsageRecord` per stage-execution per model** | Faithful: VERIFY retries and multi-model stages each get their own rows; supports every required breakdown |
| Hierarchy denormalization | **Store `work_item_id` + `project_id` on each row** at write time | Rollups avoid run→task→ancestor joins for the common case; copies the A1 owner-scoping denormalization pattern |
| Capture depth | **Full tokens (input/output/cache-read/cache-creation) + cost** | Cache hit-rate and input/output split are the main levers for reducing agent cost |
| Cost source | **Runtime-reported `total_cost_usd` / `modelUsage` cost**, never computed | No pricing table to drift; the runtime is authoritative |
| `Run.cost_usd` | **Kept**; add `total_tokens` counters beside it | Back-compat with A3 accumulation; counters are a denormalized convenience, rows are the source of truth |
| Agent-role attribution | **From `RunContext.agent` (A5c `select_agent`)**, nullable | Role is already resolved per stage; null when no agent is selected (e.g. fake runtime) |
| Budgets | **Deferred** | A5d is observability; enforcement is a separate concern (phase C) cross-referenced here |

## 4. Architecture

```
src/
  domain/
    usage.py             # PURE: TokenUsage value object (immutable combine/rollup, group_by helpers)
    runtime.py           # StageResult gains `usage: TokenUsage` (cost_usd mirrored)
    models.py            # + UsageRecord DTO; Run gains token counters
  adapters/
    runtime/
      stream_json.py     # parse() reads result.usage + result.modelUsage -> StageResult.usage
      fake.py            # result_of() carries usage; FakeAgentRuntime emits scripted usage
    database/
      orm.py             # + UsageRecordRow; RunRow gains token columns
      repositories.py    # + UsageRecordRepository
      uow.py             # + uow.usage
      ports.py           # + usage on UnitOfWork Protocol; + UsageRecord in Repository set
  interactors/
    temporal/
      activities.py      # + record_usage activity; run_stage writes usage rows + bumps Run counters
    api/
      routes/usage.py    # GET /runs/{id}/usage, /work-items/{id}/usage, /projects/{id}/usage
      deps.py            # (reuses uow dependency; no new wiring)
tests/
  unit/                  # TokenUsage math, stream_json usage parse (multi-model), rollup grouping
  integration/           # usage endpoints; rollup correctness over an epic->feature->task->run tree
  workflow/              # a faked run writes UsageRecords + bumps Run counters; idempotent on resume
```

## 5. Domain (pure, no I/O)

`domain/usage.py`:

```python
class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return (self.input_tokens + self.output_tokens
                + self.cache_read_tokens + self.cache_creation_tokens)

    def combine(self, other: "TokenUsage") -> "TokenUsage":
        # returns a NEW TokenUsage; never mutates (immutability rule)
        ...

ZERO_USAGE = TokenUsage()

def rollup(records: Iterable[TokenUsage]) -> TokenUsage: ...           # sum via combine
def group_by(records, key) -> dict[str, TokenUsage]: ...              # key = stage|agent_role|model
```

Pure, fully unit-tested, imports no adapters. `StageResult` (in `domain/runtime.py`) gains
**two** fields: `usage: TokenUsage = TokenUsage()` (the stage's combined total) and
`model_usage: dict[str, TokenUsage] = {}` (per-model breakdown, keyed by `model_id`, the
source for per-model rows in §8). Its existing `cost_usd` stays and mirrors `usage.cost_usd`
for back-compat with A3's accumulation.

## 6. Data source — extend the parser

`stream_json.parse` already special-cases the `result` event for `total_cost_usd`. Extend
that branch to read:
- `result.usage` → `input_tokens`, `output_tokens`, `cache_read_input_tokens`,
  `cache_creation_input_tokens`.
- `result.modelUsage` (map of `model_id -> {input/output/cache tokens, costUSD}`) →
  `StageResult.model_usage` (one `TokenUsage` per model) so multi-model stages persist one row
  each; the top-level `usage` block populates `StageResult.usage` (the stage total).

The fake runtime's `result_of(events)` and `FakeAgentRuntime` script a small fixed usage per
stage so the whole loop is testable without a real model. When `modelUsage` is absent,
`model_usage` falls back to `{model_id: usage}` using the run's configured `model_id` and the
top-level `usage`.

## 7. Persistence — `UsageRecord` (append-only)

`domain/models.py`:

```python
class UsageRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    run_id: str
    work_item_id: str          # the run's task (denormalized)
    project_id: str            # denormalized
    stage: RunStage
    agent_role: AgentRole | None = None
    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float = 0.0
    created_at: datetime = Field(default_factory=utc_now)
```

- `UsageRecordRow` in `orm.py`; `UsageRecordRepository` (`orm_model`/`dto`); `uow.usage`;
  Protocol additions. Append-only; never updated (same contract as `run_events`).
- Owner-scoped like every owned row; the activity supplies `owner_id` as the required filter.
- `RunRow`/`Run` gain `input_tokens`, `output_tokens`, `cache_read_tokens`,
  `cache_creation_tokens` counters (denormalized convenience beside the existing `cost_usd`).
- `create_all` picks up the new table (alembic still deferred per A1.5).

## 8. Write path (Temporal)

`run_stage` already iterates runtime events and returns `result_of(events).model_dump()`.
Extend it so that after the stage's `StageResult` is known it:
1. Resolves `work_item_id` (= `run.task_id`), `project_id`, and `agent_role` (from the
   already-selected `RunContext.agent`, nullable).
2. Calls a new **`record_usage`** activity once per entry in `StageResult.model_usage`,
   writing one `UsageRecord` per model and bumping the `Run` token counters + `cost_usd` —
   atomically in one UoW transaction (mirrors `persist_run_state`, which remains the run-state
   writer).

`record_usage` is the **only** usage writer during a run. On worker crash/resume the stage
re-runs; rows are append-only so a resumed stage that already wrote rows could double-count —
guard with an idempotency key (`run_id + stage + attempt + model_id`) on the row so
re-execution of the same attempt is a no-op insert (unique constraint → `IntegrityConflict`
swallowed as "already recorded"). `Run` counters are recomputed from rows on conflict to stay
consistent.

## 9. Read API (owner-scoped, enveloped)

A read-only `UsageService` (in `interactors/api`, wiring only — aggregation lives in
`domain/usage`) backs three endpoints, all returning the `{success, data, error}` envelope:

- `GET /runs/{id}/usage` → run totals + a per-(stage, model) breakdown list.
- `GET /work-items/{id}/usage?group_by=stage|agent_role|model` → recursive rollup over the
  item and all descendants (epic → its features → their tasks → their runs' records), using a
  descendant query over `work_items.parent_id` then `usage_records.work_item_id__in`.
- `GET /projects/{id}/usage?group_by=…&since=…&until=…` → project totals, optional grouping,
  optional `created_at` window.

`group_by` defaults to none (totals only). All queries are owner-scoped by the UoW required
filter; cross-tenant ids surface as `RecordNotFound` → 404.

## 10. Error handling

- Parser tolerates a missing/partial `usage` block — absent fields default to `0`; a stage
  with no `result` event records zero usage (and already surfaces a `fail` `StageResult`).
- `record_usage` never silently swallows write errors except the idempotency-conflict case
  (§8), which is logged as already-recorded.
- Read endpoints validate `group_by` against the allowed set (422 on invalid) and the time
  window (`since <= until`).

## 11. Testing (80% gate)

- **Domain (pure):** `TokenUsage.combine`/`total_tokens`/`rollup`/`group_by`; immutability
  (combine returns a new object).
- **Parser:** extracts top-level `usage`; splits `modelUsage` into per-model records;
  tolerates missing fields; fake `result_of` carries usage.
- **Repo:** `UsageRecord` append + owner scoping; idempotency-key conflict is a no-op.
- **Workflow (`WorkflowEnvironment`):** a faked run writes the expected rows and bumps `Run`
  counters; a resumed stage does not double-count.
- **API (integration):** the three endpoints; rollup correctness and reconciliation across a
  seeded epic → feature → task → run tree; `group_by` correctness; owner scoping; 422s.

## 12. Risks

- **Resume double-counting** — mitigated by the per-attempt idempotency key (§8); covered by a
  workflow resume test.
- **`modelUsage` shape drift** across Claude Code versions — isolated entirely in
  `stream_json.parse`; the rest of the system depends only on `TokenUsage`.
- **Rollup query cost** at large scale — acceptable now (on-read aggregation, KISS); a
  materialized-counter optimization is a later, measured change if needed.
- **Role attribution gaps** — `agent_role` is nullable; "by agent role" rollups group
  unattributed usage under a `null`/`unknown` bucket rather than failing.

## 13. Cross-references

- Spec **A5e (notifications)** consumes the §9 read service for a future budget-threshold
  alert; the trigger and budget config are defined there / in phase C, not here.
- Phase **C** budget UIs build on §7 rows and §9 endpoints; A5d intentionally stops at
  observability.
