# yaah Architecture

> **Read this before designing any task that touches persistence or the API layer.**
> It defines the target patterns (adapted from `hexrepo` `libs/db` + `libs/api`) that all
> new code must follow. The refactor plan that introduces them:
> `docs/plans/2026-06-12-yaah-a15-hexrepo-refactor.md`.

## Layering (hexagonal — unchanged)

```
ui/              # UI folder for frontend development
src/
  domain/        # pure business logic, no I/O
    models.py    # Pydantic DTOs: Project, WorkItem, Team, AgentDefinition, Run
    transitions.py  # work-item status state machine
    teams.py     # default team factory
    errors.py    # persistence-agnostic errors: RecordNotFound, IntegrityConflict
  adapters/
    database/    # ports.py (Repository/UnitOfWork protocols), ORM models, SqlRepository, SqlUnitOfWork
  interactors/
    api/         # FastAPI wiring: app factory, routes, deps, auth, envelope
  lib/           # reusable, app-agnostic modular code (e.g. CrudRouter)
```

Placement rules: domain never imports adapters or FastAPI; routes contain wiring only;
all business rules (validation, transitions) stay in domain.

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
- `Base.metadata.create_all(engine)` runs in the app factory for dev/tests; alembic
  replaces it in A6.

### Owner scoping via required filters

Hexrepo's `required_filters` mechanism is our owner-scoping enforcement: the API
dependency constructs the UoW with `required_filters={"owner_id": current_user_id}`,
and every repository query (single, list, total) automatically applies them. Routes
never hand-write `owner_id` checks.

To make this work, **every owned row carries `owner_id` — including `work_items` and
`runs`** (denormalized from the project at create time). This closes the deferred A1
gap where item-level work-item routes and run list/get were unscoped. Cross-tenant
access uniformly surfaces as `RecordNotFound` → 404.

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

## Deliberate deviations from hexrepo

| hexrepo | yaah | why |
|---|---|---|
| sync + async variants | **sync only** | YAGNI; yaah is sync SQLAlchemy until a measured need |
| `UUID` ids | **32-char uuid-hex strings** | yaah spec'd convention; no migration value |
| bare DTO / `PaginatedData` responses | **`{success, data, error}` envelope** | yaah API convention, already shipped |
| ABC base classes | **`typing.Protocol` ports** in `adapters/database/ports.py` | structural typing; deps annotate Protocol types so ports stay load-bearing. Co-located with their impl since the domain never references them |
| alembic from day one | **`create_all` until A6** | schema still fluid pre-A2 |
| read-only engine pool, query counting, relationship auto-sync (`update_relationships`), Mongo/Dynamo backends, Lambda wrapper | **omitted** | no current consumer; add when a phase needs them |
| `server_default=func.now()` timestamps | **domain-generated `utc_now()`** | timestamps are domain facts; keeps tests deterministic |

## Adding a new entity (checklist)

1. Domain DTO in `domain/models.py` (immutable updates via `model_copy`).
2. ORM row class in `adapters/database/orm.py` (`id`, `owner_id` if owned, timestamps).
3. Repository subclass in `adapters/database/repositories.py` (set `orm_model`, `dto`).
4. Property on `SqlUnitOfWork` exposing it.
5. Repository/UoW Protocol entry in `adapters/database/ports.py` if a new contract is needed.
6. `CrudRouter` (from `lib/`) instantiation in `interactors/api/routes/` + hand-written extras.
7. Integration tests through the API; unit tests only for repo behavior the API
   can't reach.
