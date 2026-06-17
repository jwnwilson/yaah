# yaah Architecture

> **Read this before designing any task that touches persistence or the API layer.**
> It defines the patterns (adapted from `hexrepo` `libs/db` + `libs/api`) that all new code
> must follow. The refactor that introduced them:
> `docs/plans/2026-06-12-yaah-a15-hexrepo-refactor.md`.
>
> For *where the project is* (what's shipped, what's dormant, what's missing), read
> [project-history.md](project-history.md) first. This file is patterns; that file is status.

## Layering (hexagonal — unchanged)

```
ui/              # React/Vite/Tailwind SPA (features/ + ui/ primitives + lib/api)
src/
  domain/        # pure business logic, no I/O — each entity model lives with its logic
    base.py          # shared id/timestamp factories (new_id, utc_now)
    projects/        # task-management domain: projects, work_items, epics (re-exported via __init__)
    runs.py · messages.py · audit.py · capabilities.py · attachments.py
    notifications.py · usage.py · refinement.py · errors.py · permissions.py · scm.py
    transitions/     # work-item + run state machines, run-stage pipeline
    orchestration/   # lead-driven orchestration DTOs/guards + orchestrator prompt contract
    agent/           # agent domain: models.py (AgentRole/Team/AgentDefinition), teams.py (default
                     #   team factory), memory.py (role memory + proposals) + execution policy:
                     #   capabilities, invocation, prompts, runtime
  adapters/
    database/    # ports.py (Repository/UnitOfWork protocols), orm, repository, uow, engine
    storage/     # StoragePort + LocalStorageAdapter (run workspaces / blobs)
    git/         # GitPort + GitForgePort: local_git, github_app, fake
    skills/      # SkillFetcher (clone/copy granted skills)
    agent/       # runtime/ (claude_code, fake, pretooluse_hook, stream_json),
                 #   model/ (anthropic, litellm, fake), refinement/, notify/
  interactors/
    api/         # FastAPI wiring: app factory, routes, deps, auth, envelope, settings
    temporal/    # workflows, activities, worker, client, config
    cli/         # seed, memory_apply (run through the same owner-scoped UoW)
  lib/           # reusable, app-agnostic modules (crud_router, secrets cipher)
```

Placement rules: domain never imports adapters or FastAPI; routes contain wiring only;
all business rules (validation, transitions, orchestration policy, capability/invocation
composition) stay in domain. Ports live beside the adapter that implements them.

**Persistence ports live with the adapter that implements them** (`adapters/database/ports.py`),
not in `domain/`. The `Repository`/`UnitOfWork` protocols are generic persistence contracts
the domain never references — they exist so consumers (routes, DI) depend on an abstraction
rather than the concrete SQLAlchemy classes. Keeping them beside `repository.py`/`uow.py`
reflects what they actually are: infrastructure interfaces, not domain ports. A true domain
port (a business-meaningful capability the domain itself calls out to) would still live in
`domain/`.

**Reusable modular code goes in `src/lib/`.** When a component is generic infrastructure
rather than feature logic — something another feature (or project) could reuse unchanged,
like the `CrudRouter` factory — it belongs in `lib/`, not buried in `interactors/`. Keep
`lib/` modules as decoupled as practical so they read as a small internal toolkit.

## Persistence: Repository + Unit of Work (from hexrepo libs/db)

### Generic repository

One generic `SqlRepository[DTO]` (in `adapters/database/repository.py`)
implements CRUD for every entity; per-entity repositories are thin declarative
subclasses:

```python
class ProjectRepository(SqlRepository[Project]):
    orm_model = ProjectRow
    dto = Project
```

Key behaviors (ported from `hexrepo_db.sql.repository.SQLRepository`, sync-only):

- **DTO in / DTO out.** Repositories accept and return domain Pydantic models, never
  ORM rows. Mapping is `dto(**row.__dict__)` on read and `orm_model(**dto.model_dump())`
  on create. Updates copy non-relationship attrs from the DTO onto the loaded row.
- **Filter DSL** on `list()`: plain key = equality; suffixes `__in`, `__like`
  (ilike contains), `__isnull`, `__gt`, `__gte`, `__lt`, `__lte`, `__ne`.
  `__isnull` replaces the old truthiness check — "root work items" is
  `{"parent_id__isnull": True}`.
- **Pagination**: `page_size` / `page_number` (1-based) + `order_by`
  (`-created_at` = descending, default). `list()` returns
  `PaginatedResult[DTO]` (`results`, `total`, `page_size`, `page_number`) — `total` is
  always computed so the UI can render page counts.
- **Typed errors, not None/bool**: `get`/`update`/`delete` raise
  `domain.errors.RecordNotFound`; constraint violations raise
  `domain.errors.IntegrityConflict`. Routes never branch on `None`.

### Unit of Work

`SqlUnitOfWork` (in `adapters/database/uow.py`) owns the session and transaction
boundary; repositories hang off it as properties sharing that one session:

```python
with uow.transaction():
    run = uow.runs.create(Run(task_id=task.id, team_id=project.team_id))
    uow.work_items.update(task.id, task.model_copy(update={"status": IN_PROGRESS}))
# both writes commit or roll back together
```

- One `transaction()` per request (provided by the API dependency). This fixes the
  A1 gap where each store method opened its own transaction (non-atomic run creation).
- The app factory owns the engine and `session_factory` (`app.state`, built once at
  startup via `adapters/database/engine.py`); the per-request dependency builds a
  `SqlUnitOfWork(session_factory, required_filters=...)`. No module-level engine map
  (hexrepo needs one for Lambda reuse; a long-lived FastAPI process does not). SQLite
  in-memory keeps `StaticPool` + `check_same_thread=False` for tests.
- **Alembic owns the schema** (`migrations/versions/`). `Base.metadata.create_all(engine)`
  remains for SQLite in-memory tests and ephemeral dev; Postgres is migrated. `make db-reset`
  clears both Postgres *and* the Temporal `temporaldata` volume, then re-seeds via
  `cli/seed.py` (see ADR-0001).

### Owner scoping via required filters

Hexrepo's `required_filters` mechanism is our owner-scoping enforcement: the API
dependency constructs the UoW with `required_filters={"owner_id": current_user_id}`,
and every repository query (single, list, total) automatically applies them. Routes
never hand-write `owner_id` checks.

To make this work, **every owned row carries `owner_id` — including `work_items` and
`runs`** (denormalized from the project at create time). This closes the deferred A1
gap where item-level work-item routes and run list/get were unscoped. Cross-tenant
access uniformly surfaces as `RecordNotFound` → 404.

## Storage port (blobs / run workspaces)

Non-relational blob storage (run workspaces, stage artifacts like `plan.md`/`progress.md`)
uses a **port co-located with its adapter**, the same convention as the database ports:

- `adapters/storage/ports.py` — `StoragePort` (a `typing.Protocol`):
  `write_bytes` / `read_text` / `exists` / `delete` / `delete_directory` / `local_path`.
  Keys are relative paths (`runs/{run_id}/plan.md`).
- `adapters/storage/local.py` — `LocalStorageAdapter(base_dir)` resolves keys under a base
  directory on the local filesystem (current backend).
- `adapters/storage/s3.py` — `S3StorageAdapter` (boto3) is the planned A4 backend; because
  callers depend only on `StoragePort`, swapping it in needs no code changes elsewhere
  (pattern adapted from `llm_api` `adapters/storage` and `hexrepo` `libs/cloud`).

A run's workspace is just the prefix `runs/{run_id}/`: Temporal activities derive the working
directory via `storage.local_path(...)` and reclaim it on terminal states via
`storage.delete_directory(...)`. There is **no separate workspace port** — workspace logic is
"just use the storage adapter (and the DB adapter) as normal." Placement rule: like the
database port, the storage port lives in `adapters/storage/ports.py`, not in `domain/`.

## API layer (from hexrepo libs/api)

### CrudRouter

`lib/crud_router.py` provides an envelope-aware port of hexrepo's
`CrudRouter`: a factory that registers standard CRUD routes for a UoW repository name —

```python
router = CrudRouter(
    repository="projects",
    response_dto=Project,
    create_schema=CreateProject,
    update_schema=UpdateProject,
    prefix="/projects",
    methods=["CREATE", "READ", "UPDATE", "DELETE"],
)
```

— generating `POST /` (201), `GET /{id}`, `GET /` (paginated list with `filters`
JSON query param, `page_size`, `page_number`, `order_by`), `PATCH /{id}`,
`DELETE /{id}`. Routes it can't express (nested creation under a project, status
transitions, run start, default team) are written by hand on the same router using
the override mechanism (`remove_api_route` + standard decorators), exactly as hexrepo
allows.

### Exception → HTTP mapping in one place

Routes and CrudRouter handlers do **not** try/except persistence errors. The app
factory registers exception handlers once:

| Exception | HTTP | Source |
|---|---|---|
| `domain.errors.RecordNotFound` | 404 | repository |
| `domain.errors.IntegrityConflict` | 409 | repository (constraint violations) |
| `domain.transitions.InvalidTransition` | 409 | state machine |
| `pydantic.ValidationError` (domain construction) | 422 | domain model validators |
| `RequestValidationError` / `HTTPException` | 422 / passthrough | FastAPI (existing) |

All handlers emit the envelope.

### Envelope and pagination meta (yaah convention, kept)

Every response stays `{success, data, error}`. List endpoints put
`PaginatedResult` bookkeeping into `meta`: `{"total": .., "page_size": ..,
"page_number": ..}` — uniform across all list endpoints (closes the A1
meta-inconsistency deferral).

## Agent execution & orchestration

Run execution is a **Temporal orchestrator-worker** system. Domain stays pure: the
non-deterministic decisions live in `domain/`, and Temporal workflows/activities are the
durable executor that carries them out.

### Ports & adapters (deny-by-default execution)

- **`AgentRuntime`** (`domain/agent/runtime.py`) — event-streaming port: a stage/step runs a
  real agent and yields `AgentEvent`s + a `StageResult` (with token `usage`). Impls:
  `ClaudeCodeRuntime` (spawns `claude -p --output-format stream-json`) and `FakeAgentRuntime`
  (scripted events, no LLM). Auto-selected by key/binary availability.
- **`ModelProvider`** (`adapters/agent/model/`) — `anthropic` (direct) or `litellm` (gateway
  with per-agent `model_alias`); chosen by `model_gateway` setting.
- **Capability composition is pure.** `domain/agent/capabilities.py` selects the agent for a
  stage (role↔stage) and assembles an `AgentManifest` from its grants; `domain/agent/
  invocation.py::build_invocation()` turns the manifest + resolved registry rows into the exact
  `claude` invocation (argv, `--append-system-prompt`, allowed tools, `settings.json` hook,
  `.mcp.json`, `YAAH_*` env, skills as (name, source, dest)). The adapter only does I/O: fetch
  skills, write files, spawn, parse. **Deny-by-default** is enforced twice — static
  `--allowedTools` and an active **PreToolUse hook** (`domain/permissions.py` decides;
  `adapters/agent/runtime/pretooluse_hook.py` enforces and logs to `audit.jsonl`).
- **Secrets** are Fernet-encrypted, write-only, and decrypted *inside the activity* into
  `manifest.secret_env` — injected into the subprocess + per-MCP `env`, never serialized into
  Temporal inputs/history, run events, or logs.

### The run path: lead-driven orchestration (ADR-0002)

`OrchestratorWorkflow` + `AgentWorkflow` are **the sole run path** (the legacy fixed-stage
`RunWorkflow` was removed in the cutover). The parent loops `invoke_lead(state)` → persist
decision/events/assignee/messages → dispatch to durable `AgentWorkflow` child actors (signal-fed
mailboxes that drain to idle) → `run_monitor(state)`, until the monitor confirms acceptance, then
opens the PR and captures memory. Human gates are Temporal signals (`approve`/`reject`/`cancel`);
the workflow is the sole writer of `run.status`. Bounded by pure `domain/orchestration` **guards**
(max waves/dispatches/messages/cost, verify rounds). The `messages` table is both the durable
mailbox and the UI inbox row. `gates_for(autonomy)` from `domain/transitions/pipeline.py` still
supplies the gate set.

Each `AgentWorkflow` returns its worst outcome + total cost; the parent records that as a truthful
per-actor report into orchestration state (fed back to the lead) and rolls it into the run cost +
cost guard.

> **Current shape:** one actor per role per wave, gathered to completion before the next wave —
> validated to the old pipeline's fidelity. True concurrent waves, quiescence/settle-window
> detection, and live agent-to-agent messaging are the **parallel-engineers** spec (the
> peer-routing id is already correct for when they land).

### Activities are the only writers

Workflows are deterministic and never touch I/O directly. All persistence (status, run_events,
usage_records, messages, audit_events, memory_proposals) flows through activities that build a
per-call owner-scoped `SqlUnitOfWork`. Usage and audit ingestion are **idempotent** (keyed by
run/stage/attempt/model and by source file) so Temporal replay/resume never double-counts.

## Deliberate deviations from hexrepo

| hexrepo | yaah | why |
|---|---|---|
| sync + async variants | **sync only** | YAGNI; yaah is sync SQLAlchemy until a measured need |
| `UUID` ids | **32-char uuid-hex strings** | yaah spec'd convention; no migration value |
| bare DTO / `PaginatedData` responses | **`{success, data, error}` envelope** | yaah API convention, already shipped |
| ABC base classes | **`typing.Protocol` ports** in `adapters/database/ports.py` | structural typing; deps annotate Protocol types so ports stay load-bearing. Co-located with their impl since the domain never references them |
| alembic from day one | **`create_all` early, alembic now** | schema was fluid pre-A2; migrations landed with A6 |
| read-only engine pool, query counting, relationship auto-sync (`update_relationships`), Mongo/Dynamo backends, Lambda wrapper | **omitted** | no current consumer; add when a phase needs them |
| `server_default=func.now()` timestamps | **domain-generated `utc_now()`** | timestamps are domain facts; keeps tests deterministic |

## Adding a new entity (checklist)

1. Domain DTO in the owning `domain/<concept>.py` module — co-located with that concept's logic, importing `new_id`/`utc_now` from `domain/base.py` (immutable updates via `model_copy`).
2. ORM row class in `adapters/database/orm.py` (`id`, `owner_id` if owned, timestamps).
3. Repository subclass in `adapters/database/repositories.py` (set `orm_model`, `dto`).
4. Property on `SqlUnitOfWork` exposing it.
5. Repository/UoW Protocol entry in `adapters/database/ports.py` if a new contract is needed.
6. `CrudRouter` (from `lib/`) instantiation in `interactors/api/routes/` + hand-written extras.
7. Integration tests through the API; unit tests only for repo behavior the API
   can't reach.
