# Role memory (A6b-3) — design

**Date:** 2026-06-16
**Status:** approved (brainstormed); implementation plan to follow
**Builds on:** A6b-1/b-2 project memory (`docs/specs/2026-06-14-a6b-1-project-memory-loop-design.md`,
`docs/specs/2026-06-14-a6b-2-memory-review-design.md`), the persistence patterns in
`docs/architecture.md` (repository / UnitOfWork / owner-scoping), and the orchestrator +
parallel-engineers feature now on `main`.

## Context

The design spec's memory model has three scopes — **Project** (`CLAUDE.md`/`docs/adr/`, shipped
in A6b as git-in-target-repo), **Role**, **Episodic**. This spec adds the **Role** scope, but —
per the decision below — stores it **in the DB with full retained history**, owner-scoped and
**cross-project**, rather than as a file in the target repo. So a role (e.g. "backend engineer")
accumulates durable learnings across **every** project and run, and nothing is overwritten/lost.

**Two regressions discovered while scoping this** (both from the orchestrator cutover, which
replaced the fixed-stage `RunWorkflow` with instruction-driven agents):

1. **Memory reading is dormant.** `build_invocation` does `if ctx.instructions: task_prompt =
   ctx.instructions` (`domain/agent/invocation.py:52-53`); every orchestrator agent passes
   `instructions`, so the `for_stage` prompt carrying the project-memory pointer is **discarded**.
2. **No LEARN curator.** `OrchestratorWorkflow` goes `verify → PR → capture_memory → DONE` with
   no curation agent.

So both the **read injection** and the **write** for role memory must happen in the orchestrator's
own instruction/persistence path (`agent_step`), not via the old `for_stage`/LEARN machinery.

## Goals / non-goals

**Goal:** durable, cross-project, per-role memory in the DB with retained history — **injected**
into a role's agent before its work (the **current project's** slice by default, the full
cross-project memory when the lead widens a dispatch's `memory_scope`) and **self-authored** by it
(written to a workspace artifact, persisted by the activity). As a near-free side effect (same
injection point), **revive the dropped project-memory read pointer**.

**Non-goals (deferred):**
- File-based role memory / the git `MemoryProposal` apply-reject flow (that's the project scope;
  DB-backed role memory does not use it).
- A dedicated LEARN-curator stage / fixing project-memory *curation* (only project *reading* is
  revived). Engineers author their **role** memory, not `CLAUDE.md`.
- Human review/approval gate before retention (auto-retain — see below), automatic
  summarization/de-dup of accumulated entries, and Episodic (`progress.md`) memory.

## Locked decisions (from brainstorming)

1. **DB-backed, cross-project, owner-scoped** — keyed by `(owner_id, role)`; accumulates across
   all projects/runs.
2. **Append-only with retained history** — every learning is a row; history is the full entry
   log; **auto-retain** (no human gate — matches "retain more information").
3. **Self-authored by the role's agent** — the agent writes learnings to a workspace artifact;
   the activity ingests it into the DB.
4. **Revive the project-memory read pointer** at the same injection point.
5. **Project-default injection, lead-widened.** Reads default to the **current project's** role
   memory; the orchestrator **lead** opts a dispatch into the full cross-project memory via a
   `memory_scope` flag (`project` default, `all` for larger/cross-cutting work). Storage stays
   cross-project + full history; only the *injected window* is project-filtered by default.

## Design

### 1. Domain model + persistence

- **`RoleMemoryEntry`** (immutable Pydantic DTO, `domain/models.py`): `id` (uuid-hex),
  `owner_id`, `role` (`AgentRole`), `content` (str), `run_id`, `project_id`, `created_at`
  (`utc_now`). Append-only — no update path.
- **`role_memory_entries`** table (owner-scoped, per `docs/architecture.md` "Adding a new
  entity"): ORM row in `adapters/database/orm.py` (`id`, `owner_id`, `role`, `content`,
  `run_id`, `project_id`, `created_at`; index on `(owner_id, role, created_at)`),
  `RoleMemoryRepository` in `repositories.py`, a `role_memory` property on `SqlUnitOfWork`, and
  an **Alembic migration**. Owner-scoping via the UoW `required_filters` mechanism is automatic.
- **Pure digest helper** (`domain/memory.py`): `role_memory_digest(entries: list[RoleMemoryEntry],
  *, max_entries: int, max_chars: int) -> str` — render the **most recent** entries (newest
  first) into a bounded markdown block, truncated to the budgets. Retention is unbounded in the
  DB; only the **injected window** is bounded, to keep prompts sane.

### 2. Read — inject role memory + revive project read (`agent_step`)

Because `ctx.instructions` overrides `for_stage`, injection happens where `agent_step` builds the
engineer brief (`interactors/temporal/activities.py`). Before the brief, `agent_step`:
1. loads the role's recent entries, **project-scoped by default**:
   `filters = {"role": role}`; add `"project_id": project_id` unless `memory_scope == "all"`;
   `list(filters, order_by="-created_at", page_size=N)` (owner-scoped automatically). So the
   default window is *this project's* `<role>` memory; `memory_scope="all"` widens it to every
   project. (`project_id` and `memory_scope` are threaded from the dispatch — see §2b.)
2. prepends a pointer + the digest, via a pure `domain/agent/prompts.py::memory_pointer(role,
   role_digest) -> str`:
   > *"Before you begin, read project memory if present (CLAUDE.md or AGENTS.md at the repo root,
   > and relevant files under docs/adr/) — honor it. Your accumulated **`<role>`** memory across
   > past work:\n`<digest>`\nApply what's relevant. If you learn something durable about working
   > as `<role>`, append a concise note (one or two lines) to `.orchestration/role-memory.md` —
   > only durable, role-level knowledge, not task specifics."*

   No role → project pointer only, no digest, no write instruction. This single change both
   **revives the project-memory read** for orchestrator agents and delivers role-memory read.

### 2b. `memory_scope` — lead opts into cross-project memory

- **`Dispatch.memory_scope`** (`domain/orchestration/core.py`): `Literal["project", "all"] =
  "project"`. Part of the lead's structured `OrchestrationDecision`; defaults to project-scoped,
  so the lead does nothing for normal work.
- **Orchestrator threads it**: `OrchestratorWorkflow`'s dispatch loop passes the dispatch's
  `memory_scope` (and the run's `project_id`) into the `AgentWorkflow` input → `agent_step`
  payload, alongside `workspace_key`/`role`.
- **Lead prompt** (`build_orchestrator_prompt`): one line documenting the field — *"For a large
  or cross-cutting task, set a dispatch's `memory_scope` to `all` so that engineer draws on its
  memory from every project; otherwise leave it `project` (the default)."*
- **Parse contract** (`parse_decision`): accept the optional field; reject an invalid value.

### 3. Write — author via artifact, persist in the activity

The sandbox has no DB access (same as decisions/verdicts/outbox), so the agent writes to a
workspace artifact and the activity ingests it:
- The pointer (above) tells the agent to append learnings to **`.orchestration/role-memory.md`**.
- After the agent runs, `agent_step` reads that artifact (reusing the existing
  `_read_artifact`-style helper / `storage.read_text`), and if non-empty persists **one**
  `RoleMemoryEntry(owner_id, role, content=<artifact text, trimmed>, run_id, project_id)`.
  One entry per role-step that produced learnings; append-only.
- `.orchestration/` is already in `WORKSPACE_SCRATCH`, so the artifact never lands in the agent's
  commit/PR — no repo pollution, and (unlike a role file) **no parallel-merge concern**: K
  same-role engineers each write their own artifact in their own workspace and each persists an
  independent DB row. The DB append model is naturally parallel-safe.

### 4. Read API (history)

A read-only, owner-scoped endpoint to view/inspect a role's memory and its history:
`GET /role-memory?role=<role>&page_size=&page_number=` → paginated `RoleMemoryEntry` list
(newest first), via the existing `CrudRouter` READ pattern or a hand-written route. No public
create (creation is internal-only, in the activity). A delete/prune endpoint and a board UI
surface are deferred.

### 5. Error handling

- **No role / no artifact / empty content:** inject project pointer only; persist nothing. Benign.
- **Persist failure** is best-effort logged; the run continues (role memory is advisory, never
  fails a stage) — mirrors the best-effort posture of audit/usage ingestion.
- **Digest bounding:** always applied so a long-lived role can't blow the prompt budget.

## Testing strategy

- **Domain (pure):** `RoleMemoryEntry` validation; `role_memory_digest` orders newest-first and
  respects `max_entries`/`max_chars`; `memory_pointer` includes the project-read pointer, the
  injected digest, and the `.orchestration/role-memory.md` write instruction (and omits the role
  parts when role is None).
- **Repository/UoW (SQLite):** append; **project-scoped** query (`role` + `project_id`) returns
  only that project's entries; **cross-project** query (`role` only) spans multiple `project_id`s;
  `order_by=-created_at`; owner isolation (other owner's rows invisible).
- **Domain (`memory_scope`):** `Dispatch.memory_scope` defaults to `"project"`; `parse_decision`
  accepts `project`/`all` and rejects an invalid value.
- **Activity:** `agent_step` injects the digest into the brief the runtime receives (capturing
  fake runtime asserts `ctx.instructions` contains the role-memory pointer); **default scope
  injects only the current project's entries, `memory_scope="all"` injects across projects**
  (seed entries under two `project_id`s and assert which appear); after a step whose agent wrote
  `.orchestration/role-memory.md`, a `RoleMemoryEntry` is persisted with the right
  `role`/`run_id`/`project_id`; empty/absent artifact persists nothing.
- **API (TestClient):** `GET /role-memory?role=backend` returns the owner's backend entries
  newest-first, paginated; owner-scoped (404/empty for another owner); rejects nothing it
  shouldn't.
- **Migration:** `alembic upgrade head` creates `role_memory_entries`; a round-trip insert/read
  works on Postgres-shaped schema (covered via the standard ORM test).

## Implementation plan (PR breakdown)

1. **Domain + persistence** — `RoleMemoryEntry` DTO, ORM row, `RoleMemoryRepository`, UoW
   property, Alembic migration, `role_memory_digest` helper + unit/repository tests. Additive,
   no behavior change.
2. **Wire read + write into `agent_step`** — `memory_pointer(role, digest)`; `Dispatch.memory_scope`
   + parse-contract + orchestrator threading (project_id/scope → `agent_step`) + lead-prompt line;
   load entries with the default project filter (or cross-project when `scope=all`) and inject;
   ingest `.orchestration/role-memory.md` → persist an entry; domain + activity tests. (Read +
   self-authoring now live.)
3. **Read API** — `GET /role-memory` (owner-scoped, paginated) + integration test. (Optional
   board-UI surface for browsing a role's memory is a later, separate increment.)

## Open risks

- **Unbounded accumulation:** the DB retains everything by design; the injected digest is bounded
  to a recent window, so prompts stay sane, but very long-lived roles will have a long tail that
  only the API surfaces. A future summarization/prune pass (or the deferred curator) can compact
  it — out of scope here.
- **Cross-project leakage of project-specific notes:** a sloppy agent could write project-specific
  content into memory. Largely mitigated by **project-default injection** — such a note only
  surfaces by default in its own project, and reaches other projects only when the lead sets
  `memory_scope=all`. Prompt wording ("role-level, not task specifics") plus a future prune UI
  are the remaining safety valves.
- **Quality drift:** auto-retain means no gate on junk. Acceptable for advisory memory that's
  injected (not executed); the read API + a future prune UI are the safety valve.
