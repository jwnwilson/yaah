# Backlog & Epic Activation — Design

**Date:** 2026-06-18
**Status:** approved (brainstorming) — pending implementation plan
**Type:** feature

## Problem

A project owner needs a place to **see, create, and modify epics → features → tasks**, groom
them until they're ready, and then **select which epics to work on**. Today the system has a
per-project execution kanban (board) and refinement chat, but no planning surface and no notion
of "selecting" epics. Runs are started one task at a time, manually. There is no way to say
"work this epic" and have the harness pick up its tasks.

## Goals

- A **backlog** view to create/groom epics, features, and tasks and assess their readiness.
- **Select epics to work on** via an `active` flag per epic.
- While an epic is active, the project **continuously auto-starts runs** for its READY tasks,
  bounded by a **per-project concurrency cap**.

## Non-goals (YAGNI)

Task dependencies/sequencing, a sprint/iteration entity, manual priority ordering, cross-project
scheduling, story points/estimates, and auto-retry of failed tasks. None of these are built.

## Concept / mental model

Two views over the same project hierarchy:

- **Backlog** (new, planning) — a list of *epics* with readiness indicators, where you
  create/groom epics → features → tasks and toggle which epics are **active**.
- **Board** (existing, execution) — the kanban, unchanged.

"Select epics to work on" = flipping an `active` flag on an epic. While an epic is active, the
project continuously auto-starts runs for its READY tasks, up to a per-project concurrency cap.
"Prepare to be worked on" = ordinary grooming (write body/acceptance-criteria, split into tasks,
move tasks to READY). The backlog view *surfaces* readiness; it introduces no new grooming
mechanics.

### Decisions captured in brainstorming

| Question | Decision |
|----------|----------|
| What does selecting an epic do? | An **`active` flag** on the epic (backlog = inactive epics). |
| How does work start? | **Auto-start** runs for READY tasks when active. |
| One-shot or continuous? | **Continuous policy** — any task that becomes READY while the epic is active auto-starts. |
| Concurrency | **Per-project `max_concurrent_runs`** cap; excess READY tasks wait. |
| Scheduler architecture | **Stateless reconciliation** (DB is source of truth). |

## The queue is derived (no new entity)

- **Queued** = READY tasks whose owning epic is active and that have no in-flight run.
- **In-flight** = runs in a non-terminal status (`PENDING`, `RUNNING`, `AWAITING_APPROVAL`,
  `BLOCKED`) in the project.
- **Free slots** = `max(0, max_concurrent_runs − in_flight)`.
- **Order** = FIFO by `created_at` (no manual priority).
- **A task's owning epic**: the task's `parent` is either the epic directly, or a feature whose
  `parent` is the epic.

## Data model

Two new fields; no new tables.

- `WorkItem.active: bool = False` — meaningful only for epics. A model validator rejects
  `active=True` when `kind != EPIC`.
- `Project.max_concurrent_runs: int = 2` — must be ≥ 1.

ORM: add the two columns (`work_item_row.active`, `project_row.max_concurrent_runs`) with
defaults so existing rows backfill cleanly.

**No change to the work-item or run state machines** — `active` is orthogonal to `status`.

## Scheduler — stateless reconciliation

### Pure policy (`domain/projects/scheduling.py`, no I/O)

```
plan_starts(ready_task_ids_ordered: list[str], in_flight: int, limit: int) -> list[str]
    # returns ready_task_ids_ordered[: max(0, limit - in_flight)]

owning_epic_id(task: WorkItem, features_by_id: dict[str, WorkItem]) -> str
    # resolves a task to its epic via direct parent or its feature's parent
```

Both are pure and fully unit-testable.

### Interactor `reconcile_project(project_id)`

1. Open a transaction that **locks the project row** (`SELECT … FOR UPDATE`) to serialize
   concurrent reconciles for the same project.
2. Recompute: active epics → their feature ids → READY tasks under `(epic_ids ∪ feature_ids)`
   ordered by `created_at`, minus tasks that already have an in-flight run; count in-flight runs.
3. Call `plan_starts(...)`.
4. Start each selected task via the **shared run-trigger path**.

### Shared run-trigger path

The existing run-creation logic in the runs route is refactored into a reusable interactor
`start_run(uow, task, project, settings, temporal_client)` that: validates the task is a READY
`TASK`, moves it to `IN_PROGRESS`, creates the `Run`, and starts the `OrchestratorWorkflow`. Both
the manual `POST /work-items/{task_id}/runs` endpoint and the scheduler call this one path.

### Triggers (each just calls `reconcile_project`)

1. **Epic activate/deactivate** — after the flag flips.
2. **Task → READY** — in the existing `set_status` endpoint, after a successful transition to
   `READY`.
3. **Run reaches terminal state** — a final `reconcile_project` step at the end of the run
   workflow (an activity) fills the freed slot.

Reconciliation is idempotent and self-healing: every trigger re-derives correct state from the DB.

### Concurrency correctness

The per-project row lock guarantees that two concurrent reconciles cannot both observe the same
free slot and double-start. Counting in-flight runs and starting new ones happens inside the
locked transaction.

## API additions

- `POST /projects/{project_id}/epics/{epic_id}/activate` → sets `active=True`, reconciles, returns
  the epic. 404 if not an epic in the project.
- `POST /projects/{project_id}/epics/{epic_id}/deactivate` → sets `active=False`, returns the epic.
  (No reconcile needed; deactivation never starts work.)
- `UpdateProject` gains `max_concurrent_runs` (existing `PATCH /projects/{id}`). Changing it
  triggers a reconcile (raising the cap should pull more work).
- `GET /projects/{project_id}/backlog` → backlog read-model in one call:
  - per epic: `{ epic, active, ready_count, total_tasks, done, in_flight_count }`
  - project summary: `{ max_concurrent_runs, in_flight, queued }`

  Extends the existing epic-board aggregation.

## UI

New route `/projects/:projectId/backlog`, in the nav alongside the board.

- **Header**: editable `max_concurrent_runs`; live indicator "running X / N · queued Y".
- **Epic list**: active epics on top, backlog (inactive) below. Each row: title, an **active
  toggle**, readiness (`R ready / T tasks · D done`) with a progress bar, and a link to open the
  epic on the board for grooming.
- **Create epic** inline; epic/feature/task editing reuses the existing `HierarchyTree` and
  `TicketPanel`.
- Building blocks: `Card`, `Badge`, `Button`, `Field`, existing React Query key factories
  (`epicKeys`, `workItemKeys`), and a new `backlogKeys`/`useBacklog` hook + `activateEpic`/
  `deactivateEpic` API calls.
- The existing Board is unchanged.

## Behavior decisions (defaults)

- **Deactivating** an epic stops new starts; **in-flight runs keep running**.
- **Failed task** stays `FAILED` (not `READY`); it will not re-run until moved back to `READY`,
  after which the continuous policy retries it. No silent auto-retry.
- **`AWAITING_APPROVAL` holds a slot** (counts as in-flight) — gated runs occupy capacity until
  the user acts.
- **Activating an epic with zero READY tasks** is allowed (no-op until tasks are groomed; the UI
  shows "nothing ready").

## Testing

- **Unit**: `plan_starts` permutations (limit/in-flight/queue sizes incl. 0 and overflow);
  `owning_epic_id` resolution (task under epic vs under feature); `active` validator
  (non-epic rejected); reconcile selects the correct READY tasks and skips tasks with in-flight
  runs.
- **Integration (API via TestClient + `FakeAgentRuntime`)**:
  - activate epic with N ready tasks and limit M → exactly M runs start, the rest stay READY
    (queued);
  - a task moved to READY under an active epic with a free slot → starts; with no free slot →
    queues;
  - a run reaching terminal state frees a slot → the next queued task starts;
  - deactivate halts new starts; in-flight runs are untouched;
  - concurrency cap is never exceeded;
  - owner-scoping (cannot activate/reconcile another owner's project).
- 80% coverage gate; `make lint` green.

## Rollout / migration

Additive schema change (two nullable-with-default columns); no data migration beyond column
defaults. Feature is inert until an epic is activated, so it ships dark by default
(`active=False`, `max_concurrent_runs=2`).

## Open questions for review

1. Should `AWAITING_APPROVAL` count against the concurrency cap (current default: yes)?
2. Default `max_concurrent_runs` value (current default: 2).
3. Backlog as a separate route vs a tab within the board page (current default: separate route).
