# yaah A1.5 — Hexrepo-Pattern Refactor (DB Adapter + API Layer) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hand-written per-entity stores and per-route error handling with the hexrepo patterns — generic `SqlRepository`, `SqlUnitOfWork` with required-filter owner scoping, typed domain errors mapped to HTTP once, and an envelope-aware `CrudRouter` — closing the A1 deferred gaps (item-level owner scoping, run-creation atomicity, pagination meta, Query bounds) in the process.

**Architecture:** See `docs/architecture.md` (read it first — it is the spec for this plan). Strangler sequence: build the new stack alongside the old (Tasks 1–7), cut routes over module-by-module (Tasks 8–12), delete the legacy stores last (Task 13). The API test suite must stay green after every task.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 ORM (sync), pytest.

**Branch:** create `feature/a15-hexrepo-refactor` off the latest A1 branch before Task 1:
```bash
git checkout feature/a1-control-plane && git checkout -b feature/a15-hexrepo-refactor
git add docs/architecture.md CLAUDE.md docs/plans/2026-06-12-yaah-a15-hexrepo-refactor.md
git commit -m "docs: architecture.md (hexrepo patterns) + A1.5 refactor plan"
```

**Git rules for every task:** stay on `feature/a15-hexrepo-refactor`; never rename branches, push, or rewrite history; stage files explicitly by path (never `git add -A`).

**API contract changes (intentional, pre-A2):**
- List endpoints take `page_size` (1–200, default 50) / `page_number` (≥1) / `order_by` (default `-created_at`) instead of `limit`/`offset`; CrudRouter lists also take a `filters` JSON query param.
- List `meta` becomes `{"total": int, "page_size": int, "page_number": int}`.
- Everything else (paths, envelope, status codes incl. DELETE→200 with `{"deleted": id}`) is unchanged.

---

### Task 1: Domain errors

**Files:**
- Create: `src/domain/errors.py`
- Test: `tests/unit/test_errors.py`

- [ ] **Step 1: Write the failing test** (`tests/unit/test_errors.py`)

```python
import pytest

from domain.errors import IntegrityConflict, InvalidFilter, RecordNotFound, RepositoryError


@pytest.mark.parametrize("exc", [RecordNotFound, IntegrityConflict, InvalidFilter])
def test_errors_are_repository_errors(exc):
    with pytest.raises(RepositoryError):
        raise exc("boom")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_errors.py -v` — Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement** (`src/domain/errors.py`)

```python
class RepositoryError(Exception):
    """Base for persistence-layer errors surfaced to the domain."""


class RecordNotFound(RepositoryError):
    pass


class IntegrityConflict(RepositoryError):
    pass


class InvalidFilter(RepositoryError):
    pass
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/unit/test_errors.py -v` — Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/domain/errors.py tests/unit/test_errors.py
git commit -m "feat: typed domain persistence errors"
```

---

### Task 2: owner_id on WorkItem and Run

**Files:**
- Modify: `src/domain/models.py` (WorkItem, Run)
- Modify: `tests/unit/test_models.py`, `tests/unit/test_teams.py` (constructor updates)

- [ ] **Step 1: Update the tests first.** In `tests/unit/test_models.py`, every `WorkItem(...)` constructor gains `owner_id="dev-user"`, e.g.:

```python
def test_work_item_defaults_to_draft():
    w = WorkItem(owner_id="dev-user", project_id="p1", kind=WorkItemKind.EPIC, title="Auth")
    assert w.status == WorkItemStatus.DRAFT
    assert w.acceptance_criteria == []
```

(Apply the same `owner_id="dev-user"` addition to `test_epic_cannot_have_parent` and `test_task_requires_parent`.) Add one new test:

```python
def test_work_item_requires_owner():
    with pytest.raises(ValidationError):
        WorkItem(project_id="p1", kind=WorkItemKind.EPIC, title="x")
```

In `tests/unit/test_teams.py`, `test_run_defaults` becomes:

```python
def test_run_defaults():
    r = Run(owner_id="dev-user", task_id="t1", team_id="tm1")
    assert r.status == RunStatus.PENDING
    assert r.cost_usd == 0.0
    assert r.stage is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_models.py tests/unit/test_teams.py -v` — Expected: new/updated tests FAIL (ValidationError not raised / unexpected keyword accepted? — the `owner_id=` constructors fail with "extra" only if strict; the required-owner test fails because the field doesn't exist yet).

- [ ] **Step 3: Implement.** In `src/domain/models.py` add `owner_id: str` as the second field of both `WorkItem` and `Run` (right after `id`), mirroring `Project.owner_id`.

- [ ] **Step 4: Run to verify pass.** `uv run pytest tests/unit -q` — Expected: unit suite green EXCEPT `tests/unit/test_stores.py::test_work_item_filters` and `tests/unit/test_stores_teams_runs.py::test_run_roundtrip_and_update` (legacy stores now must persist owner_id). Patch those two tests' constructors with `owner_id="u1"` and add `Column("owner_id", String(64), nullable=False, index=True)` to the `work_items` and `runs` tables in `src/adapters/database/tables.py` (legacy file — it is deleted in Task 13, but the suite must stay green until then). Integration tests: the work-items and runs routes construct WorkItem/Run — add `owner_id=user_id` at the construction sites in `src/interactors/api/routes/work_items.py` (`WorkItem(project_id=project_id, owner_id=user_id, **body.model_dump())`) and `src/interactors/api/routes/runs.py` (`Run(task_id=task_id, team_id=project.team_id, owner_id=project.owner_id)`). Re-run `uv run pytest -q` — Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add src/domain/models.py src/adapters/database/tables.py \
  src/interactors/api/routes/work_items.py src/interactors/api/routes/runs.py \
  tests/unit/test_models.py tests/unit/test_teams.py \
  tests/unit/test_stores.py tests/unit/test_stores_teams_runs.py
git commit -m "feat: owner_id on WorkItem and Run (every owned row carries owner_id)"
```

---

### Task 3: Ports rewrite — PaginatedResult, Repository, UnitOfWork protocols

**Files:**
- Modify: `src/domain/ports.py` (full rewrite — nothing imports the old protocols)

- [ ] **Step 1: Replace `src/domain/ports.py` entirely:**

```python
from contextlib import AbstractContextManager
from typing import Any, Generic, Protocol, TypeVar

from pydantic import BaseModel

from domain.models import AgentDefinition, Project, Run, Team, WorkItem

DTO = TypeVar("DTO", bound=BaseModel)


class PaginatedResult(BaseModel, Generic[DTO]):
    results: list[DTO]
    total: int
    page_size: int
    page_number: int


class Repository(Protocol[DTO]):
    def create(self, obj: DTO) -> DTO: ...
    def get(self, entity_id: str) -> DTO: ...
    def list(
        self,
        filters: dict[str, Any] | None = None,
        page_size: int = 50,
        page_number: int = 1,
        order_by: str | None = None,
    ) -> PaginatedResult[DTO]: ...
    def update(self, entity_id: str, obj: DTO) -> DTO: ...
    def delete(self, entity_id: str) -> None: ...
    def delete_many(self, filters: dict[str, Any]) -> int: ...


class UnitOfWork(Protocol):
    def transaction(self) -> AbstractContextManager["UnitOfWork"]: ...

    @property
    def projects(self) -> Repository[Project]: ...
    @property
    def work_items(self) -> Repository[WorkItem]: ...
    @property
    def teams(self) -> Repository[Team]: ...
    @property
    def agents(self) -> Repository[AgentDefinition]: ...
    @property
    def runs(self) -> Repository[Run]: ...
```

- [ ] **Step 2: Verify it imports, run the suite, commit**

```bash
uv run python -c "import domain.ports" && uv run pytest -q
git add src/domain/ports.py
git commit -m "refactor: ports as Repository/UnitOfWork protocols with PaginatedResult"
```

---

### Task 4: Declarative ORM models

**Files:**
- Create: `src/adapters/database/orm.py`
- Test: `tests/unit/test_orm.py`

- [ ] **Step 1: Write the failing test** (`tests/unit/test_orm.py`)

```python
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from adapters.database.orm import Base, ProjectRow, WorkItemRow


def test_create_all_and_roundtrip():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            ProjectRow(
                id="a" * 32, owner_id="u1", name="p", repo_url="r",
                local_path=None, team_id=None, autonomy="gated_all",
                created_at=__import__("domain.models", fromlist=["utc_now"]).utc_now(),
            )
        )
        session.commit()
        row = session.execute(select(ProjectRow)).scalar_one()
        assert row.owner_id == "u1"


def test_work_item_row_has_owner_id_column():
    assert "owner_id" in WorkItemRow.__table__.columns
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_orm.py -v` — Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement** (`src/adapters/database/orm.py`) — same columns as the legacy `tables.py` (including the Task-2 owner_id additions), as mapped classes:

```python
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    repo_url: Mapped[str | None] = mapped_column(String(500))
    local_path: Mapped[str | None] = mapped_column(String(500))
    team_id: Mapped[str | None] = mapped_column(String(32))
    autonomy: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorkItemRow(Base):
    __tablename__ = "work_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    acceptance_criteria: Mapped[list] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TeamRow(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentDefinitionRow(Base):
    __tablename__ = "agent_definitions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    team_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    persona: Mapped[str] = mapped_column(Text, nullable=False, default="")
    model_alias: Mapped[str] = mapped_column(String(100), nullable=False)
    runtime: Mapped[str] = mapped_column(String(50), nullable=False)


class RunRow(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    team_id: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    stage: Mapped[str | None] = mapped_column(String(30))
    branch: Mapped[str | None] = mapped_column(String(200))
    pr_url: Mapped[str | None] = mapped_column(String(500))
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

> Note: `orm.py` uses its own `Base.metadata`, so it can coexist with the legacy
> `tables.py` metadata until Task 13. Table names are identical — old and new code are
> never active against the same app instance at the same time during the cutover tasks.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/unit/test_orm.py -v` — Expected: 2 PASS. Then `uv run pytest -q` — full suite green.

- [ ] **Step 5: Commit**

```bash
git add src/adapters/database/orm.py tests/unit/test_orm.py
git commit -m "feat: declarative ORM row models (owner_id on all owned tables)"
```

---

### Task 5: Generic SqlRepository

**Files:**
- Create: `src/adapters/database/repository.py`
- Test: `tests/unit/test_repository.py`

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_repository.py`)

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from adapters.database.orm import Base, ProjectRow
from adapters.database.repository import SqlRepository
from domain.errors import InvalidFilter, RecordNotFound
from domain.models import Project


class ProjectRepo(SqlRepository[Project]):
    orm_model = ProjectRow
    dto = Project


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as s:
        yield s


def _repo(session: Session, owner: str | None = "u1") -> ProjectRepo:
    required = {"owner_id": owner} if owner else None
    return ProjectRepo(session, required_filters=required)


def _project(name: str, owner: str = "u1") -> Project:
    return Project(owner_id=owner, name=name, repo_url="r")


def test_create_get_roundtrip(session):
    repo = _repo(session)
    created = repo.create(_project("a"))
    assert repo.get(created.id).name == "a"


def test_get_missing_raises_record_not_found(session):
    with pytest.raises(RecordNotFound):
        _repo(session).get("nope")


def test_required_filters_scope_get_and_list(session):
    repo_u1 = _repo(session, "u1")
    p = repo_u1.create(_project("mine"))
    repo_u2 = _repo(session, "u2")
    with pytest.raises(RecordNotFound):
        repo_u2.get(p.id)
    assert repo_u2.list().total == 0
    assert repo_u1.list().total == 1


def test_filter_dsl(session):
    repo = _repo(session)
    a = repo.create(_project("alpha"))
    repo.create(_project("beta"))
    assert repo.list(filters={"name": "alpha"}).results[0].id == a.id
    assert repo.list(filters={"name__in": ["alpha"]}).total == 1
    assert repo.list(filters={"name__like": "ALP"}).total == 1
    assert repo.list(filters={"team_id__isnull": True}).total == 2
    assert repo.list(filters={"name__ne": "alpha"}).results[0].name == "beta"


def test_invalid_filter_key_raises(session):
    with pytest.raises(InvalidFilter):
        _repo(session).list(filters={"nope": 1})


def test_pagination_and_order(session):
    repo = _repo(session)
    for n in ["a", "b", "c"]:
        repo.create(_project(n))
    page = repo.list(page_size=2, page_number=2, order_by="name")
    assert page.total == 3
    assert [p.name for p in page.results] == ["c"]
    assert repo.list(order_by="-name").results[0].name == "c"


def test_update_copies_fields_but_not_owner(session):
    repo = _repo(session)
    p = repo.create(_project("a"))
    hijack = p.model_copy(update={"name": "b", "owner_id": "evil"})
    updated = repo.update(p.id, hijack)
    assert updated.name == "b"
    assert updated.owner_id == "u1"


def test_delete_and_delete_many(session):
    repo = _repo(session)
    p = repo.create(_project("a"))
    repo.create(_project("b"))
    repo.delete(p.id)
    with pytest.raises(RecordNotFound):
        repo.get(p.id)
    assert repo.delete_many({"name": "b"}) == 1
    assert repo.list().total == 0
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_repository.py -v` — Expected: FAIL (ImportError).

- [ ] **Step 3: Implement** (`src/adapters/database/repository.py`)

```python
from typing import Any, Callable, ClassVar, Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy import Select, asc, desc, func, select
from sqlalchemy.exc import IntegrityError as SQLIntegrityError
from sqlalchemy.orm import Session

from adapters.database.orm import Base
from domain.errors import IntegrityConflict, InvalidFilter, RecordNotFound
from domain.ports import PaginatedResult

DTO = TypeVar("DTO", bound=BaseModel)

_OPS: dict[str, Callable[[Any, Any], Any]] = {
    "eq": lambda col, v: col == v,
    "ne": lambda col, v: col != v,
    "in": lambda col, v: col.in_(v),
    "like": lambda col, v: col.ilike(f"%{v}%"),
    "isnull": lambda col, v: col.is_(None) if v else col.isnot(None),
    "gt": lambda col, v: col > v,
    "gte": lambda col, v: col >= v,
    "lt": lambda col, v: col < v,
    "lte": lambda col, v: col <= v,
}


class SqlRepository(Generic[DTO]):
    """Generic CRUD over one ORM row class, returning domain DTOs.

    Subclasses set `orm_model` and `dto`. `required_filters` (e.g. owner_id)
    are applied to every query, so cross-tenant rows are invisible.
    """

    orm_model: ClassVar[type[Base]]
    dto: type[DTO]
    default_order_by: ClassVar[str] = "-created_at"

    def __init__(self, session: Session, required_filters: dict[str, Any] | None = None):
        self._session = session
        self._required_filters = required_filters or {}

    def _column(self, name: str) -> Any:
        col = getattr(self.orm_model, name, None)
        if col is None:
            raise InvalidFilter(f"unknown field: {name}")
        return col

    def _scoped(self) -> Select[Any]:
        query = select(self.orm_model)
        for key, value in self._required_filters.items():
            if hasattr(self.orm_model, key):
                query = query.where(getattr(self.orm_model, key) == value)
        return query

    def _filtered(self, query: Select[Any], filters: dict[str, Any]) -> Select[Any]:
        for key, value in filters.items():
            field, _, op = key.rpartition("__")
            if not field or op not in _OPS:
                field, op = key, "eq"
            query = query.where(_OPS[op](self._column(field), value))
        return query

    def _ordered(self, query: Select[Any], order_by: str) -> Select[Any]:
        direction = desc if order_by.startswith("-") else asc
        return query.order_by(direction(self._column(order_by.lstrip("-"))))

    def _row(self, entity_id: str) -> Any:
        row = self._session.execute(
            self._scoped().where(self.orm_model.id == entity_id)
        ).scalar_one_or_none()
        if row is None:
            raise RecordNotFound(f"{self.dto.__name__} {entity_id} not found")
        return row

    def _to_dto(self, row: Any) -> DTO:
        return self.dto(**{k: v for k, v in row.__dict__.items() if not k.startswith("_")})

    def create(self, obj: DTO) -> DTO:
        row = self.orm_model(**obj.model_dump())
        try:
            self._session.add(row)
            self._session.flush()
        except SQLIntegrityError as err:
            raise IntegrityConflict(str(err.orig)) from err
        return self._to_dto(row)

    def get(self, entity_id: str) -> DTO:
        return self._to_dto(self._row(entity_id))

    def list(
        self,
        filters: dict[str, Any] | None = None,
        page_size: int = 50,
        page_number: int = 1,
        order_by: str | None = None,
    ) -> PaginatedResult[DTO]:
        query = self._filtered(self._scoped(), filters or {})
        total = int(self._session.scalar(select(func.count()).select_from(query.subquery())))
        query = self._ordered(query, order_by or self.default_order_by)
        query = query.limit(page_size).offset((page_number - 1) * page_size)
        rows = self._session.execute(query).scalars().all()
        return PaginatedResult[self.dto](  # type: ignore[misc]
            results=[self._to_dto(r) for r in rows],
            total=total,
            page_size=page_size,
            page_number=page_number,
        )

    def update(self, entity_id: str, obj: DTO) -> DTO:
        row = self._row(entity_id)
        for key, value in obj.model_dump(exclude={"id", "owner_id", "created_at"}).items():
            setattr(row, key, value)
        try:
            self._session.flush()
        except SQLIntegrityError as err:
            raise IntegrityConflict(str(err.orig)) from err
        return self._to_dto(row)

    def delete(self, entity_id: str) -> None:
        self._session.delete(self._row(entity_id))
        self._session.flush()

    def delete_many(self, filters: dict[str, Any]) -> int:
        rows = self._session.execute(self._filtered(self._scoped(), filters)).scalars().all()
        for row in rows:
            self._session.delete(row)
        self._session.flush()
        return len(rows)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/unit/test_repository.py -v` — Expected: 9 PASS. Then `uv run pytest -q` green.

- [ ] **Step 5: Commit**

```bash
git add src/adapters/database/repository.py tests/unit/test_repository.py
git commit -m "feat: generic SqlRepository with filter DSL, pagination, required-filter scoping"
```

---

### Task 6: Entity repositories

**Files:**
- Create: `src/adapters/database/repositories.py`
- Test: `tests/unit/test_repositories.py`

- [ ] **Step 1: Write the failing test** (`tests/unit/test_repositories.py`)

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.database.orm import Base
from adapters.database.repositories import AgentDefinitionRepository, WorkItemRepository
from domain.models import AgentDefinition, AgentRole, WorkItem, WorkItemKind


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_work_item_repo_filters_by_kind_and_parent():
    s = _session()
    repo = WorkItemRepository(s, required_filters={"owner_id": "u1"})
    epic = repo.create(WorkItem(owner_id="u1", project_id="p1", kind=WorkItemKind.EPIC, title="E"))
    task = repo.create(
        WorkItem(owner_id="u1", project_id="p1", kind=WorkItemKind.TASK,
                 parent_id=epic.id, title="T")
    )
    assert repo.list(filters={"kind": "task"}).results[0].id == task.id
    assert repo.list(filters={"parent_id__isnull": True}).results[0].id == epic.id


def test_agent_repo_is_not_owner_scoped_and_orders_by_id():
    s = _session()
    repo = AgentDefinitionRepository(s, required_filters={"owner_id": "u1"})
    repo.create(AgentDefinition(team_id="t1", role=AgentRole.LEAD, name="L", model_alias="m"))
    assert repo.list(filters={"team_id": "t1"}).total == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_repositories.py -v` — Expected: FAIL (ImportError).

- [ ] **Step 3: Implement** (`src/adapters/database/repositories.py`)

```python
from adapters.database.orm import (
    AgentDefinitionRow,
    ProjectRow,
    RunRow,
    TeamRow,
    WorkItemRow,
)
from adapters.database.repository import SqlRepository
from domain.models import AgentDefinition, Project, Run, Team, WorkItem


class ProjectRepository(SqlRepository[Project]):
    orm_model = ProjectRow
    dto = Project


class WorkItemRepository(SqlRepository[WorkItem]):
    orm_model = WorkItemRow
    dto = WorkItem


class TeamRepository(SqlRepository[Team]):
    orm_model = TeamRow
    dto = Team


class AgentDefinitionRepository(SqlRepository[AgentDefinition]):
    # Not owner-scoped: agents are reached through their (owner-scoped) team,
    # and AgentDefinitionRow has no owner_id column — _scoped() skips absent keys.
    orm_model = AgentDefinitionRow
    dto = AgentDefinition
    default_order_by = "id"


class RunRepository(SqlRepository[Run]):
    orm_model = RunRow
    dto = Run
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/unit/test_repositories.py -v` — Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/adapters/database/repositories.py tests/unit/test_repositories.py
git commit -m "feat: per-entity repositories as SqlRepository subclasses"
```

---

### Task 7: SqlUnitOfWork

**Files:**
- Create: `src/adapters/database/uow.py`
- Test: `tests/unit/test_uow.py`

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_uow.py`)

```python
import pytest

from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.models import Project, Run


def _uow(owner: str = "u1") -> SqlUnitOfWork:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return SqlUnitOfWork(make_session_factory(engine), required_filters={"owner_id": owner})


def test_transaction_commits_across_repositories():
    uow = _uow()
    with uow.transaction():
        p = uow.projects.create(Project(owner_id="u1", name="p", repo_url="r"))
        uow.runs.create(Run(owner_id="u1", task_id="t1", team_id="tm1"))
    with uow.transaction():
        assert uow.projects.get(p.id).name == "p"
        assert uow.runs.list(filters={"task_id": "t1"}).total == 1


def test_transaction_rolls_back_all_writes_on_error():
    uow = _uow()
    with pytest.raises(RuntimeError):
        with uow.transaction():
            uow.projects.create(Project(owner_id="u1", name="p", repo_url="r"))
            raise RuntimeError("boom")
    with uow.transaction():
        assert uow.projects.list().total == 0


def test_repository_access_outside_transaction_fails():
    uow = _uow()
    with pytest.raises(RuntimeError):
        _ = uow.projects


def test_nested_transaction_rejected():
    uow = _uow()
    with uow.transaction():
        with pytest.raises(RuntimeError):
            with uow.transaction():
                pass
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_uow.py -v` — Expected: FAIL (ImportError).

- [ ] **Step 3: Implement** (`src/adapters/database/uow.py`)

```python
import contextlib
from typing import Any, Iterator

from sqlalchemy.orm import Session, sessionmaker

from adapters.database.repositories import (
    AgentDefinitionRepository,
    ProjectRepository,
    RunRepository,
    TeamRepository,
    WorkItemRepository,
)


class SqlUnitOfWork:
    """One session/transaction shared by all repositories. The app factory owns
    the engine/session_factory; one UoW is built per request with the caller's
    required filters (owner scoping)."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        required_filters: dict[str, Any] | None = None,
    ):
        self._session_factory = session_factory
        self._required_filters = required_filters or {}
        self._session: Session | None = None

    @contextlib.contextmanager
    def transaction(self) -> Iterator["SqlUnitOfWork"]:
        if self._session is not None:
            raise RuntimeError("transaction already in progress")
        self._session = self._session_factory()
        try:
            yield self
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        finally:
            self._session.close()
            self._session = None

    @property
    def session(self) -> Session:
        if self._session is None:
            raise RuntimeError("no active transaction")
        return self._session

    @property
    def projects(self) -> ProjectRepository:
        return ProjectRepository(self.session, self._required_filters)

    @property
    def work_items(self) -> WorkItemRepository:
        return WorkItemRepository(self.session, self._required_filters)

    @property
    def teams(self) -> TeamRepository:
        return TeamRepository(self.session, self._required_filters)

    @property
    def agents(self) -> AgentDefinitionRepository:
        return AgentDefinitionRepository(self.session, self._required_filters)

    @property
    def runs(self) -> RunRepository:
        return RunRepository(self.session, self._required_filters)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/unit/test_uow.py -v` — Expected: 4 PASS. Full suite green.

- [ ] **Step 5: Commit**

```bash
git add src/adapters/database/uow.py tests/unit/test_uow.py
git commit -m "feat: SqlUnitOfWork — shared transaction, owner-scoped repositories"
```

---

### Task 8: App wiring — exception handlers + get_uow dependency

**Files:**
- Modify: `src/interactors/api/app.py`, `src/interactors/api/deps.py`
- Test: `tests/integration/test_app.py` (additions)

- [ ] **Step 1: Add failing tests** to `tests/integration/test_app.py`:

```python
def test_record_not_found_maps_to_404_envelope():
    app = create_app(Settings(_env_file=None, database_url="sqlite:///:memory:"))

    from domain.errors import RecordNotFound

    @app.get("/_boom")
    def boom() -> dict:
        raise RecordNotFound("Project x not found")

    resp = TestClient(app, raise_server_exceptions=False).get("/_boom")
    assert resp.status_code == 404
    assert resp.json() == {"success": False, "data": None, "error": "Project x not found"}


def test_integrity_conflict_maps_to_409():
    app = create_app(Settings(_env_file=None, database_url="sqlite:///:memory:"))

    from domain.errors import IntegrityConflict

    @app.get("/_conflict")
    def conflict() -> dict:
        raise IntegrityConflict("duplicate")

    resp = TestClient(app, raise_server_exceptions=False).get("/_conflict")
    assert resp.status_code == 409
```

(Add `from fastapi.testclient import TestClient` import note: already imported in this file.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/integration/test_app.py -v` — Expected: new tests FAIL (500).

- [ ] **Step 3: Implement.** In `src/interactors/api/app.py`, inside `create_app` (after the existing handlers), register:

```python
    from domain.errors import IntegrityConflict, InvalidFilter, RecordNotFound
    from domain.transitions import InvalidTransition

    def _envelope_handler(status_code: int):
        async def handler(_: Request, exc: Exception) -> JSONResponse:
            return JSONResponse(status_code=status_code, content=err(str(exc)))

        return handler

    app.add_exception_handler(RecordNotFound, _envelope_handler(404))
    app.add_exception_handler(IntegrityConflict, _envelope_handler(409))
    app.add_exception_handler(InvalidTransition, _envelope_handler(409))
    app.add_exception_handler(InvalidFilter, _envelope_handler(400))
```

Also in `create_app`: ensure the new ORM metadata is created alongside the legacy one (until Task 13 removes the legacy):

```python
    from adapters.database.orm import Base

    Base.metadata.create_all(engine)
```

In `src/interactors/api/deps.py`, ADD (keep the existing store providers until Task 13):

```python
from fastapi import Depends

from adapters.database.uow import SqlUnitOfWork
from domain.ports import UnitOfWork
from interactors.api.auth import current_user_id


def get_uow(request: Request, user_id: str = Depends(current_user_id)) -> UnitOfWork:
    return SqlUnitOfWork(
        request.app.state.session_factory,
        required_filters={"owner_id": user_id},
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -q` — Expected: all green (new tests pass, no regressions).

- [ ] **Step 5: Commit**

```bash
git add src/interactors/api/app.py src/interactors/api/deps.py tests/integration/test_app.py
git commit -m "feat: domain-error exception handlers + owner-scoped UoW dependency"
```

---

### Task 9: CrudRouter + projects cutover

**Files:**
- Create: `src/interactors/api/crud_router.py`
- Rewrite: `src/interactors/api/routes/projects.py`
- Modify: `tests/integration/test_projects_api.py` (only if an assertion touches removed behavior)

- [ ] **Step 1: Run the existing projects tests as the (currently green) safety net**

Run: `uv run pytest tests/integration/test_projects_api.py -v` — Expected: PASS (these must STILL pass at the end of the task; they are the spec).

- [ ] **Step 2: Implement** (`src/interactors/api/crud_router.py`)

```python
import json
from typing import Any, Callable

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from domain.errors import InvalidFilter
from domain.models import utc_now
from domain.ports import UnitOfWork
from interactors.api.auth import current_user_id
from interactors.api.deps import get_uow
from interactors.api.envelope import ok


class CrudRouter(APIRouter):
    """Envelope-aware port of hexrepo's CrudRouter (see docs/architecture.md).

    Generates standard CRUD routes backed by a UnitOfWork repository. Custom
    routes override generated ones via the decorator methods below, which
    remove the colliding generated route first.
    """

    def __init__(
        self,
        *,
        repository: str,
        response_dto: type[BaseModel],
        create_schema: type[BaseModel] | None = None,
        update_schema: type[BaseModel] | None = None,
        methods: tuple[str, ...] = ("READ",),
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.repository = repository
        self.response_dto = response_dto
        self.create_schema = create_schema
        self.update_schema = update_schema
        self._setup(methods)

    def _setup(self, methods: tuple[str, ...]) -> None:
        if "CREATE" in methods:
            self.add_api_route("", self._create(), methods=["POST"], status_code=201)
        if "READ" in methods:
            self.add_api_route("", self._list(), methods=["GET"])
            self.add_api_route("/{entity_id}", self._read(), methods=["GET"])
        if "UPDATE" in methods:
            self.add_api_route("/{entity_id}", self._update(), methods=["PATCH"])
        if "DELETE" in methods:
            self.add_api_route("/{entity_id}", self._delete(), methods=["DELETE"])

    def _create(self) -> Callable[..., dict]:
        create_schema, dto, repo_name = self.create_schema, self.response_dto, self.repository

        def handler(
            body: create_schema,  # type: ignore[valid-type]
            user_id: str = Depends(current_user_id),
            uow: UnitOfWork = Depends(get_uow),
        ) -> dict:
            obj = dto(owner_id=user_id, **body.model_dump())
            with uow.transaction():
                created = getattr(uow, repo_name).create(obj)
            return ok(created.model_dump(mode="json"))

        return handler

    def _read(self) -> Callable[..., dict]:
        repo_name = self.repository

        def handler(entity_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
            with uow.transaction():
                obj = getattr(uow, repo_name).get(entity_id)
            return ok(obj.model_dump(mode="json"))

        return handler

    def _list(self) -> Callable[..., dict]:
        repo_name = self.repository

        def handler(
            filters: str = "{}",
            page_size: int = Query(50, ge=1, le=200),
            page_number: int = Query(1, ge=1),
            order_by: str = "-created_at",
            uow: UnitOfWork = Depends(get_uow),
        ) -> dict:
            try:
                parsed: dict[str, Any] = json.loads(filters)
            except json.JSONDecodeError as exc:
                raise InvalidFilter(f"filters must be a JSON object: {exc}") from exc
            with uow.transaction():
                page = getattr(uow, repo_name).list(
                    filters=parsed, page_size=page_size,
                    page_number=page_number, order_by=order_by,
                )
            return ok(
                [r.model_dump(mode="json") for r in page.results],
                meta={"total": page.total, "page_size": page.page_size,
                      "page_number": page.page_number},
            )

        return handler

    def _update(self) -> Callable[..., dict]:
        update_schema, repo_name = self.update_schema, self.repository

        def handler(
            entity_id: str,
            body: update_schema,  # type: ignore[valid-type]
            uow: UnitOfWork = Depends(get_uow),
        ) -> dict:
            with uow.transaction():
                repo = getattr(uow, repo_name)
                current = repo.get(entity_id)
                changes = body.model_dump(exclude_none=True)
                if "updated_at" in current.model_fields:
                    changes["updated_at"] = utc_now()
                updated = repo.update(entity_id, current.model_copy(update=changes))
            return ok(updated.model_dump(mode="json"))

        return handler

    def _delete(self) -> Callable[..., dict]:
        repo_name = self.repository

        def handler(entity_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
            with uow.transaction():
                getattr(uow, repo_name).delete(entity_id)
            return ok({"deleted": entity_id})

        return handler

    def _remove_route(self, path: str, methods: list[str]) -> None:
        wanted = set(methods)
        for route in list(self.routes):
            if route.path == f"{self.prefix}{path}" and route.methods == wanted:  # type: ignore[attr-defined]
                self.routes.remove(route)

    def get(self, path: str, *args: Any, **kwargs: Any) -> Callable:  # type: ignore[override]
        self._remove_route(path, ["GET"])
        return super().get(path, *args, **kwargs)

    def post(self, path: str, *args: Any, **kwargs: Any) -> Callable:  # type: ignore[override]
        self._remove_route(path, ["POST"])
        return super().post(path, *args, **kwargs)

    def patch(self, path: str, *args: Any, **kwargs: Any) -> Callable:  # type: ignore[override]
        self._remove_route(path, ["PATCH"])
        return super().patch(path, *args, **kwargs)

    def delete(self, path: str, *args: Any, **kwargs: Any) -> Callable:  # type: ignore[override]
        self._remove_route(path, ["DELETE"])
        return super().delete(path, *args, **kwargs)
```

- [ ] **Step 3: Rewrite** `src/interactors/api/routes/projects.py`:

```python
from fastapi import Depends

from domain.models import AutonomyLevel, Project
from domain.ports import UnitOfWork
from interactors.api.crud_router import CrudRouter
from interactors.api.deps import get_uow
from interactors.api.envelope import ok
from pydantic import BaseModel


class CreateProject(BaseModel):
    name: str
    repo_url: str | None = None
    local_path: str | None = None
    autonomy: AutonomyLevel = AutonomyLevel.GATED_ALL


class UpdateProject(BaseModel):
    name: str | None = None
    team_id: str | None = None
    autonomy: AutonomyLevel | None = None


router = CrudRouter(
    repository="projects",
    response_dto=Project,
    create_schema=CreateProject,
    update_schema=UpdateProject,
    methods=("CREATE", "READ", "UPDATE", "DELETE"),
    prefix="/projects",
    tags=["projects"],
)


@router.delete("/{project_id}")
def delete_project(project_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    """Override: cascade child work items in the same transaction."""
    with uow.transaction():
        uow.projects.get(project_id)  # 404 (RecordNotFound) if absent/not owned
        uow.work_items.delete_many({"project_id": project_id})
        uow.projects.delete(project_id)
    return ok({"deleted": project_id})
```

> Note: domain `ValidationError` from `Project(...)` construction (e.g. missing repo)
> propagates to FastAPI as a 500 unless handled — `pydantic.ValidationError` must map
> to 422. Add to the Task 8 handler block in `app.py` (do it now, same commit):
> ```python
> from pydantic import ValidationError
> app.add_exception_handler(ValidationError, _envelope_handler(422))
> ```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/integration/test_projects_api.py tests/integration/test_work_items_api.py -v` — Expected: ALL PASS unchanged (including `test_delete_project_cascades_work_items` and `test_create_project_requires_a_repo` → 422). Then full suite: `uv run pytest -q` green.

- [ ] **Step 5: Commit**

```bash
git add src/interactors/api/crud_router.py src/interactors/api/routes/projects.py src/interactors/api/app.py
git commit -m "feat: envelope-aware CrudRouter; projects routes on UnitOfWork"
```

---

### Task 10: Work-items cutover

**Files:**
- Rewrite: `src/interactors/api/routes/work_items.py`

- [ ] **Step 1: Safety net** — `uv run pytest tests/integration/test_work_items_api.py -v` must be green before AND after.

- [ ] **Step 2: Rewrite** `src/interactors/api/routes/work_items.py`:

```python
from fastapi import APIRouter, Depends, Query

from domain.models import WorkItem, WorkItemKind, WorkItemStatus, utc_now
from domain.ports import UnitOfWork
from domain.transitions import validate_transition
from interactors.api.deps import get_uow
from interactors.api.envelope import ok
from pydantic import BaseModel

router = APIRouter(tags=["work-items"])


class CreateWorkItem(BaseModel):
    kind: WorkItemKind
    title: str
    body: str = ""
    parent_id: str | None = None
    acceptance_criteria: list[str] = []


class UpdateWorkItem(BaseModel):
    title: str | None = None
    body: str | None = None
    acceptance_criteria: list[str] | None = None


class SetStatus(BaseModel):
    status: WorkItemStatus


@router.post("/projects/{project_id}/work-items", status_code=201)
def create(project_id: str, body: CreateWorkItem, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        project = uow.projects.get(project_id)  # RecordNotFound -> 404
        item = WorkItem(project_id=project_id, owner_id=project.owner_id, **body.model_dump())
        created = uow.work_items.create(item)
    return ok(created.model_dump(mode="json"))


@router.get("/projects/{project_id}/work-items")
def list_items(
    project_id: str,
    kind: WorkItemKind | None = None,
    status: WorkItemStatus | None = None,
    parent_id: str | None = None,
    page_size: int = Query(100, ge=1, le=200),
    page_number: int = Query(1, ge=1),
    uow: UnitOfWork = Depends(get_uow),
) -> dict:
    filters: dict = {"project_id": project_id}
    if kind:
        filters["kind"] = kind
    if status:
        filters["status"] = status
    if parent_id:
        filters["parent_id"] = parent_id
    with uow.transaction():
        uow.projects.get(project_id)  # RecordNotFound -> 404
        page = uow.work_items.list(
            filters=filters, page_size=page_size, page_number=page_number,
            order_by="created_at",
        )
    return ok(
        [i.model_dump(mode="json") for i in page.results],
        meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number},
    )


@router.patch("/work-items/{item_id}")
def patch(item_id: str, body: UpdateWorkItem, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        item = uow.work_items.get(item_id)  # owner-scoped: cross-tenant -> 404
        updated = item.model_copy(
            update={**body.model_dump(exclude_none=True), "updated_at": utc_now()}
        )
        result = uow.work_items.update(item_id, updated)
    return ok(result.model_dump(mode="json"))


@router.post("/work-items/{item_id}/status")
def set_status(item_id: str, body: SetStatus, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        item = uow.work_items.get(item_id)
        validate_transition(item.status, body.status)  # InvalidTransition -> 409
        updated = item.model_copy(update={"status": body.status, "updated_at": utc_now()})
        result = uow.work_items.update(item_id, updated)
    return ok(result.model_dump(mode="json"))


@router.delete("/work-items/{item_id}")
def delete(item_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        uow.work_items.delete(item_id)  # get+delete, owner-scoped
    return ok({"deleted": item_id})
```

- [ ] **Step 3: Run to verify pass**

Run: `uv run pytest tests/integration/test_work_items_api.py tests/integration/test_projects_api.py -v` — Expected: ALL PASS unchanged (404s now come from `RecordNotFound`, 409 from `InvalidTransition`, 422 from domain `ValidationError` — same envelope and codes). Full suite green.

- [ ] **Step 4: Commit**

```bash
git add src/interactors/api/routes/work_items.py
git commit -m "refactor: work-items routes on UnitOfWork (owner-scoped item routes)"
```

---

### Task 11: Teams cutover

**Files:**
- Rewrite: `src/interactors/api/routes/teams.py`

- [ ] **Step 1: Safety net** — `uv run pytest tests/integration/test_teams_api.py -v` green before AND after.

- [ ] **Step 2: Rewrite** `src/interactors/api/routes/teams.py`:

```python
from fastapi import APIRouter, Depends

from domain.ports import UnitOfWork
from domain.teams import default_team
from interactors.api.auth import current_user_id
from interactors.api.deps import get_uow
from interactors.api.envelope import ok

router = APIRouter(prefix="/teams", tags=["teams"])


@router.post("/default", status_code=201)
def create_default(
    user_id: str = Depends(current_user_id),
    uow: UnitOfWork = Depends(get_uow),
) -> dict:
    team, agents = default_team(owner_id=user_id)
    with uow.transaction():
        uow.teams.create(team)
        stored_agents = [uow.agents.create(agent) for agent in agents]
    return ok(
        {
            "team": team.model_dump(mode="json"),
            "agents": [a.model_dump(mode="json") for a in stored_agents],
        }
    )


@router.get("")
def list_teams(uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        page = uow.teams.list()
    return ok(
        [t.model_dump(mode="json") for t in page.results],
        meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number},
    )


@router.get("/{team_id}")
def get(team_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        team = uow.teams.get(team_id)  # RecordNotFound -> 404
        agents = uow.agents.list(filters={"team_id": team_id}).results
    return ok(
        {
            "team": team.model_dump(mode="json"),
            "agents": [a.model_dump(mode="json") for a in agents],
        }
    )
```

- [ ] **Step 3: Fix agent ordering in `get`.** The test asserts roles `["lead", "backend", "qa"]`, but `AgentDefinitionRepository.default_order_by = "id"` sorts by random uuid-hex, so fetched order is nondeterministic. `AgentDefinition` has no `created_at`, so sort in the route by `AgentRole` declaration order (lead < architect < backend < frontend < qa < devops), which is the canonical team order. Add to `teams.py`:

```python
from domain.models import AgentRole

_ROLE_ORDER = {role: index for index, role in enumerate(AgentRole)}
```

and in `get`, replace the `agents = ...` line with:

```python
        agents = sorted(
            uow.agents.list(filters={"team_id": team_id}).results,
            key=lambda a: _ROLE_ORDER[a.role],
        )
```

- [ ] **Step 4: Run to verify pass.** `uv run pytest tests/integration/test_teams_api.py -v` — PASS unchanged (nested shape preserved, deterministic role order). Full suite green.

- [ ] **Step 5: Commit**

```bash
git add src/interactors/api/routes/teams.py
git commit -m "refactor: teams routes on UnitOfWork (atomic team+agents creation)"
```

---

### Task 12: Runs cutover (atomic run start)

**Files:**
- Rewrite: `src/interactors/api/routes/runs.py`
- Modify: `tests/integration/test_runs_api.py` (one strengthened assertion)

- [ ] **Step 1: Strengthen the test first** (replaces the comment-only "task moved to in_progress" check noted in the A1 review). In `tests/integration/test_runs_api.py`, change `_ready_task` to also return the project id — final line becomes `return task["id"], team_id, pid` — and update both call sites: `task_id, team_id, pid = _ready_task(c)` in `test_start_run_on_ready_task` and `task_id, _, _ = _ready_task(c)` in `test_run_rejected_unless_task_ready`. Then in `test_start_run_on_ready_task`, replace the `# task moved to in_progress` comment with a real assertion:

```python
    items = c.get(f"/projects/{pid}/work-items", params={"kind": "task"}).json()["data"]
    assert items[0]["status"] == "in_progress"
```

Run: `uv run pytest tests/integration/test_runs_api.py -v` — Expected: still PASS (behavior already true; this locks it).

- [ ] **Step 2: Rewrite** `src/interactors/api/routes/runs.py`:

```python
from fastapi import APIRouter, Depends, HTTPException

from domain.models import Run, WorkItemKind, WorkItemStatus, utc_now
from domain.ports import UnitOfWork
from interactors.api.deps import get_uow
from interactors.api.envelope import ok

router = APIRouter(tags=["runs"])


@router.post("/work-items/{task_id}/runs", status_code=201)
def start_run(task_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        task = uow.work_items.get(task_id)  # RecordNotFound -> 404 (owner-scoped)
        if task.kind != WorkItemKind.TASK:
            raise HTTPException(status_code=404, detail="task not found")
        if task.status != WorkItemStatus.READY:
            raise HTTPException(status_code=409, detail=f"task is {task.status}, must be ready")
        project = uow.projects.get(task.project_id)
        if not project.team_id:
            raise HTTPException(status_code=409, detail="project has no team assigned")
        run = uow.runs.create(
            Run(owner_id=project.owner_id, task_id=task_id, team_id=project.team_id)
        )
        uow.work_items.update(
            task_id,
            task.model_copy(update={"status": WorkItemStatus.IN_PROGRESS, "updated_at": utc_now()}),
        )
    # run insert + task transition commit or roll back together (closes the A1 atomicity gap)
    return ok(run.model_dump(mode="json"))


@router.get("/work-items/{task_id}/runs")
def list_runs(task_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        uow.work_items.get(task_id)  # 404 for unknown task (unifies list semantics)
        page = uow.runs.list(filters={"task_id": task_id}, order_by="-created_at")
    return ok(
        [r.model_dump(mode="json") for r in page.results],
        meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number},
    )


@router.get("/runs/{run_id}")
def get_run(run_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        run = uow.runs.get(run_id)  # owner-scoped -> cross-tenant 404
    return ok(run.model_dump(mode="json"))
```

> Note: `HTTPException` raised inside `uow.transaction()` triggers rollback (any
> exception does) before FastAPI renders it — correct and intended.

- [ ] **Step 3: Run to verify pass**

Run: `uv run pytest tests/integration/test_runs_api.py -v` — Expected: ALL PASS, including the error-branch tests (`POST` on missing/non-task → 404 via RecordNotFound/explicit, no-team → 409, missing run → 404). Full suite green.

- [ ] **Step 4: Commit**

```bash
git add src/interactors/api/routes/runs.py tests/integration/test_runs_api.py
git commit -m "refactor: runs routes on UnitOfWork — atomic run start + task transition"
```

---

### Task 13: Delete legacy layer + final gates

**Files:**
- Delete: `src/adapters/database/stores.py`, `src/adapters/database/tables.py`, `tests/unit/test_stores.py`, `tests/unit/test_stores_teams_runs.py`
- Modify: `src/interactors/api/deps.py` (remove store providers), `src/interactors/api/app.py` (remove legacy `metadata.create_all`), `CLAUDE.md` (architecture tree)

- [ ] **Step 1: Remove legacy code.**

```bash
git rm src/adapters/database/stores.py src/adapters/database/tables.py \
  tests/unit/test_stores.py tests/unit/test_stores_teams_runs.py
```

In `src/interactors/api/deps.py` delete the four legacy providers (`project_store`, `work_item_store`, `team_store`, `run_store`) and the `adapters.database.stores` import — `get_uow` remains the only dependency. In `src/interactors/api/app.py` remove `from adapters.database.tables import metadata` and the `metadata.create_all(engine)` line, keeping `Base.metadata.create_all(engine)`.

- [ ] **Step 2: Update the CLAUDE.md architecture tree** — replace the `adapters/` lines with:

```
  adapters/      # concrete port implementations
    database/    # orm.py (rows), repository.py (generic), repositories.py, uow.py, engine.py
```

- [ ] **Step 3: Full gates**

```bash
uv run pytest -q          # all green
make coverage             # >= 80% (expect ~97%)
make lint                 # clean
uv run ruff format --check src tests
```

- [ ] **Step 4: Live smoke test against Postgres** (schema changed: drop the dev volume so create_all builds the new columns)

```bash
docker compose down -v && docker compose up -d postgres && sleep 5
uv run uvicorn --app-dir src interactors.api.app:create_app --factory --port 8100 &
sleep 2 && curl -s localhost:8100/health
curl -s -X POST localhost:8100/projects -H 'content-type: application/json' \
  -d '{"name":"smoke","repo_url":"r"}'
kill %1
```

Expected: health envelope OK; project create returns 201 envelope with `owner_id: "dev-user"`.

- [ ] **Step 5: Commit**

```bash
git add -u
git add CLAUDE.md
git commit -m "refactor: remove legacy stores/tables; UnitOfWork is the only persistence path"
```

(`git add -u` is acceptable here ONLY because Step 1's `git rm` already staged deletions and the remaining changes are the two named files; verify with `git status --short` that nothing unrelated is staged before committing.)

---

## Deferred (do NOT build in this plan)

- Alembic migration baseline (A6 — `create_all` stays until then).
- Async repository/UoW variants, read-only engine pool, query counting (no consumer).
- JSON-filters query param on the nested work-items list (typed params kept for contract stability).
- Cross-tenant API integration tests (need a second authenticated user — Auth0 phase).
- `conftest.py` extraction of `make_client` (separate small chore; avoid churning every test file in this refactor).
