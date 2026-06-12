# yaah A1 — Control-Plane Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the yaah repo with its domain model, Postgres persistence, and a FastAPI CRUD API for projects, work items (epics/features/tasks), teams, and runs — the foundation every later phase builds on.

**Architecture:** New standalone repo at `/Users/noel/projects/yaah`, hexagonal like llm_api: `src/domain` (pure logic + ports), `src/adapters/database` (SQLAlchemy), `src/interactors/api` (FastAPI wiring). Single `work_items` table models the epic→feature→task hierarchy via `kind` + `parent_id`. Status changes go through a domain state machine. Auth is a dependency that injects `dev-user` in local mode (Auth0 slots in later); every owned row carries `owner_id` from day one.

**Tech Stack:** Python 3.12, uv, FastAPI, Pydantic v2, SQLAlchemy 2.0 (sync), Postgres 16 (SQLite in-memory for tests), pytest + httpx.

**Spec:** `docs/specs/2026-06-12-yaah-design.md`

---

### Task 1: Repo scaffold

**Files:**
- Create: `/Users/noel/projects/yaah/pyproject.toml`, `.gitignore`, `README.md`, `src/domain/__init__.py`, `src/adapters/__init__.py`, `src/interactors/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`

- [ ] **Step 1: Create repo and structure**

```bash
cd /Users/noel/projects/yaah  # repo, git, CLAUDE.md and docs/ already exist
mkdir -p src/domain src/adapters/database src/interactors/api/routes tests/unit tests/integration docs/specs docs/plans
touch src/__init__.py src/domain/__init__.py src/adapters/__init__.py src/adapters/database/__init__.py \
  src/interactors/__init__.py src/interactors/api/__init__.py src/interactors/api/routes/__init__.py \
  tests/__init__.py tests/unit/__init__.py tests/integration/__init__.py
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "yaah"
version = "0.1.0"
description = "Agent harness: virtual dev teams driven from a task board"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "pydantic>=2.9",
    "sqlalchemy>=2.0",
    "psycopg[binary]>=3.2",
    "pydantic-settings>=2.6",
]

[dependency-groups]
dev = ["pytest>=8.3", "httpx>=0.27", "pytest-cov>=5.0", "ruff>=0.7"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
src = ["src", "tests"]
```

- [ ] **Step 3: Write `.gitignore`**

```
__pycache__/
*.pyc
.venv/
.env
.pytest_cache/
.ruff_cache/
htmlcov/
.coverage
```

- [ ] **Step 4: Write `README.md`**

```markdown
# yaah

Self-hosted agent harness: virtual dev teams (lead, engineers, QA, …) that take
tickets from a kanban board and produce reviewed PRs, in sandboxed containers,
on user-configurable models.

Design spec: `docs/specs/2026-06-12-agent-harness-design.md`

## Stack
Python 3.12 / uv / FastAPI / SQLAlchemy / Postgres / Temporal / React (UI in `ui/`, later phase).

## Dev
```bash
uv sync
docker compose up -d postgres
uv run pytest
uv run uvicorn --app-dir src interactors.api.app:create_app --factory --reload
```
```

- [ ] **Step 5: Install and verify pytest runs**

```bash
cd /Users/noel/projects/yaah && uv sync && uv run pytest
```
Expected: `no tests ran` (exit code 5 is fine).

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "chore: scaffold yaah repo (hexagonal layout, uv, pytest)"
```

---

### Task 2: docker-compose + settings

**Files:**
- Create: `docker-compose.yml`, `.env.example`, `src/interactors/api/settings.py`
- Test: `tests/unit/test_settings.py`

- [ ] **Step 1: Write `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: yaah
      POSTGRES_PASSWORD: yaah
      POSTGRES_DB: yaah
    ports:
      - "5433:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U yaah"]
      interval: 5s
      timeout: 3s
      retries: 10

volumes:
  pgdata:
```

- [ ] **Step 2: Write `.env.example`**

```
YAAH_PROFILE=local            # local | remote
YAAH_DATABASE_URL=postgresql+psycopg://yaah:yaah@localhost:5433/yaah
YAAH_AUTH_MODE=dev            # dev | auth0
```

- [ ] **Step 3: Write the failing test** (`tests/unit/test_settings.py`)

```python
from interactors.api.settings import Settings


def test_settings_defaults_to_local_dev():
    s = Settings(_env_file=None)
    assert s.profile == "local"
    assert s.auth_mode == "dev"
    assert s.database_url.startswith("postgresql+psycopg://")


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("YAAH_PROFILE", "remote")
    monkeypatch.setenv("YAAH_AUTH_MODE", "auth0")
    s = Settings(_env_file=None)
    assert s.profile == "remote"
    assert s.auth_mode == "auth0"
```

- [ ] **Step 4: Run to verify it fails**

Run: `uv run pytest tests/unit/test_settings.py -v` — Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 5: Implement** (`src/interactors/api/settings.py`)

```python
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="YAAH_", env_file=".env")

    profile: Literal["local", "remote"] = "local"
    auth_mode: Literal["dev", "auth0"] = "dev"
    database_url: str = "postgresql+psycopg://yaah:yaah@localhost:5433/yaah"
```

- [ ] **Step 6: Run to verify it passes**

Run: `uv run pytest tests/unit/test_settings.py -v` — Expected: 2 PASS.

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat: docker-compose postgres + typed settings with profiles"
```

---

### Task 3: Domain enums and core models

**Files:**
- Create: `src/domain/models.py`
- Test: `tests/unit/test_models.py`

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_models.py`)

```python
import pytest
from pydantic import ValidationError

from domain.models import (
    AgentRole,
    AutonomyLevel,
    Project,
    WorkItem,
    WorkItemKind,
    WorkItemStatus,
)


def test_project_gets_id_and_defaults():
    p = Project(owner_id="dev-user", name="llm_api", repo_url="https://github.com/x/llm_api")
    assert len(p.id) == 32  # uuid hex
    assert p.autonomy == AutonomyLevel.GATED_ALL


def test_project_requires_repo_url_or_local_path():
    with pytest.raises(ValidationError):
        Project(owner_id="dev-user", name="nowhere")


def test_work_item_defaults_to_draft():
    w = WorkItem(project_id="p1", kind=WorkItemKind.EPIC, title="Auth")
    assert w.status == WorkItemStatus.DRAFT
    assert w.acceptance_criteria == []


def test_epic_cannot_have_parent():
    with pytest.raises(ValidationError):
        WorkItem(project_id="p1", kind=WorkItemKind.EPIC, title="x", parent_id="other")


def test_task_requires_parent():
    with pytest.raises(ValidationError):
        WorkItem(project_id="p1", kind=WorkItemKind.TASK, title="x")


def test_roles_enum_has_core_roles():
    assert {"lead", "architect", "backend", "frontend", "qa", "devops"} <= {r.value for r in AgentRole}
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_models.py -v` — Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement** (`src/domain/models.py`)

```python
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def new_id() -> str:
    return uuid4().hex


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AutonomyLevel(StrEnum):
    GATED_ALL = "gated_all"
    GATED_MERGE = "gated_merge"
    FULL_AUTO = "full_auto"


class WorkItemKind(StrEnum):
    EPIC = "epic"
    FEATURE = "feature"
    TASK = "task"


class WorkItemStatus(StrEnum):
    DRAFT = "draft"
    REFINING = "refining"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    DONE = "done"
    BLOCKED = "blocked"
    FAILED = "failed"


class AgentRole(StrEnum):
    LEAD = "lead"
    ARCHITECT = "architect"
    BACKEND = "backend"
    FRONTEND = "frontend"
    QA = "qa"
    DEVOPS = "devops"


class Project(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    name: str
    repo_url: str | None = None
    local_path: str | None = None
    team_id: str | None = None
    autonomy: AutonomyLevel = AutonomyLevel.GATED_ALL
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _needs_a_repo(self) -> "Project":
        if not self.repo_url and not self.local_path:
            raise ValueError("project needs repo_url or local_path")
        return self


class WorkItem(BaseModel):
    id: str = Field(default_factory=new_id)
    project_id: str
    kind: WorkItemKind
    parent_id: str | None = None
    title: str
    body: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    status: WorkItemStatus = WorkItemStatus.DRAFT
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _hierarchy_rules(self) -> "WorkItem":
        if self.kind == WorkItemKind.EPIC and self.parent_id:
            raise ValueError("epics cannot have a parent")
        if self.kind in (WorkItemKind.FEATURE, WorkItemKind.TASK) and not self.parent_id:
            raise ValueError(f"{self.kind} requires parent_id")
        return self
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/unit/test_models.py -v` — Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: domain models for projects and work-item hierarchy"
```

---

### Task 4: Team, agent, and run models + default team factory

**Files:**
- Modify: `src/domain/models.py` (append)
- Create: `src/domain/teams.py`
- Test: `tests/unit/test_teams.py`

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_teams.py`)

```python
from domain.models import AgentRole, Run, RunStatus, Team
from domain.teams import default_team


def test_default_team_has_lead_engineer_qa():
    team, agents = default_team(owner_id="dev-user")
    assert isinstance(team, Team)
    roles = [a.role for a in agents]
    assert roles == [AgentRole.LEAD, AgentRole.BACKEND, AgentRole.QA]
    assert all(a.team_id == team.id for a in agents)


def test_default_team_model_aliases_follow_role_rubric():
    _, agents = default_team(owner_id="dev-user")
    by_role = {a.role: a.model_alias for a in agents}
    assert by_role[AgentRole.LEAD] == "lead-model"
    assert by_role[AgentRole.BACKEND] == "engineer-model"
    assert by_role[AgentRole.QA] == "qa-model"


def test_run_defaults():
    r = Run(task_id="t1", team_id="tm1")
    assert r.status == RunStatus.PENDING
    assert r.cost_usd == 0.0
    assert r.stage is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_teams.py -v` — Expected: FAIL (ImportError).

- [ ] **Step 3: Append to `src/domain/models.py`**

```python
class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    DONE = "done"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class Team(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    name: str
    created_at: datetime = Field(default_factory=utc_now)


class AgentDefinition(BaseModel):
    id: str = Field(default_factory=new_id)
    team_id: str
    role: AgentRole
    name: str
    persona: str = ""
    model_alias: str
    runtime: str = "claude_code"


class Run(BaseModel):
    id: str = Field(default_factory=new_id)
    task_id: str
    team_id: str
    status: RunStatus = RunStatus.PENDING
    stage: str | None = None
    branch: str | None = None
    pr_url: str | None = None
    cost_usd: float = 0.0
    created_at: datetime = Field(default_factory=utc_now)
```

- [ ] **Step 4: Implement `src/domain/teams.py`**

```python
from domain.models import AgentDefinition, AgentRole, Team

_DEFAULT_AGENTS: list[tuple[AgentRole, str, str]] = [
    (AgentRole.LEAD, "Lead", "lead-model"),
    (AgentRole.BACKEND, "Engineer", "engineer-model"),
    (AgentRole.QA, "QA", "qa-model"),
]


def default_team(owner_id: str, name: str = "Default Team") -> tuple[Team, list[AgentDefinition]]:
    """The Phase-A starter team: lead + engineer + QA (spec §10)."""
    team = Team(owner_id=owner_id, name=name)
    agents = [
        AgentDefinition(team_id=team.id, role=role, name=agent_name, model_alias=alias)
        for role, agent_name, alias in _DEFAULT_AGENTS
    ]
    return team, agents
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/unit/test_teams.py -v` — Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: team/agent/run models and default lead+engineer+qa team"
```

---

### Task 5: Work-item status state machine

**Files:**
- Create: `src/domain/transitions.py`
- Test: `tests/unit/test_transitions.py`

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_transitions.py`)

```python
import pytest

from domain.models import WorkItemStatus as S
from domain.transitions import InvalidTransition, validate_transition


@pytest.mark.parametrize(
    "src,dst",
    [
        (S.DRAFT, S.REFINING),
        (S.DRAFT, S.READY),
        (S.REFINING, S.READY),
        (S.READY, S.IN_PROGRESS),
        (S.IN_PROGRESS, S.IN_REVIEW),
        (S.IN_PROGRESS, S.BLOCKED),
        (S.IN_PROGRESS, S.FAILED),
        (S.IN_REVIEW, S.APPROVED),
        (S.IN_REVIEW, S.IN_PROGRESS),
        (S.APPROVED, S.DONE),
        (S.BLOCKED, S.READY),
        (S.FAILED, S.READY),
    ],
)
def test_valid_transitions(src, dst):
    validate_transition(src, dst)  # must not raise


@pytest.mark.parametrize(
    "src,dst",
    [(S.DRAFT, S.DONE), (S.READY, S.DONE), (S.DONE, S.IN_PROGRESS), (S.DRAFT, S.IN_REVIEW)],
)
def test_invalid_transitions_raise(src, dst):
    with pytest.raises(InvalidTransition):
        validate_transition(src, dst)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_transitions.py -v` — Expected: FAIL (ImportError).

- [ ] **Step 3: Implement** (`src/domain/transitions.py`)

```python
from domain.models import WorkItemStatus as S


class InvalidTransition(Exception):
    pass


_ALLOWED: dict[S, set[S]] = {
    S.DRAFT: {S.REFINING, S.READY},
    S.REFINING: {S.READY, S.DRAFT},
    S.READY: {S.IN_PROGRESS, S.DRAFT},
    S.IN_PROGRESS: {S.IN_REVIEW, S.BLOCKED, S.FAILED},
    S.IN_REVIEW: {S.APPROVED, S.IN_PROGRESS},
    S.APPROVED: {S.DONE},
    S.BLOCKED: {S.READY},
    S.FAILED: {S.READY},
    S.DONE: set(),
}


def validate_transition(src: S, dst: S) -> None:
    if dst not in _ALLOWED[src]:
        raise InvalidTransition(f"cannot move work item from {src} to {dst}")
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/unit/test_transitions.py -v` — Expected: 16 PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: work-item status state machine"
```

---

### Task 6: Store ports

**Files:**
- Create: `src/domain/ports.py`

- [ ] **Step 1: Implement** (`src/domain/ports.py`) — typing-only module; covered by adapter tests in Tasks 7–8.

```python
from typing import Protocol

from domain.models import Project, Run, Team, AgentDefinition, WorkItem, WorkItemKind, WorkItemStatus


class ProjectStore(Protocol):
    def add(self, project: Project) -> Project: ...
    def get(self, project_id: str, owner_id: str) -> Project | None: ...
    def list(self, owner_id: str, limit: int = 50, offset: int = 0) -> list[Project]: ...
    def update(self, project: Project) -> Project: ...
    def delete(self, project_id: str, owner_id: str) -> bool: ...


class WorkItemStore(Protocol):
    def add(self, item: WorkItem) -> WorkItem: ...
    def get(self, item_id: str) -> WorkItem | None: ...
    def list(
        self,
        project_id: str,
        kind: WorkItemKind | None = None,
        status: WorkItemStatus | None = None,
        parent_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[WorkItem]: ...
    def update(self, item: WorkItem) -> WorkItem: ...
    def delete(self, item_id: str) -> bool: ...


class TeamStore(Protocol):
    def add(self, team: Team, agents: list[AgentDefinition]) -> Team: ...
    def get(self, team_id: str, owner_id: str) -> Team | None: ...
    def list(self, owner_id: str) -> list[Team]: ...
    def agents(self, team_id: str) -> list[AgentDefinition]: ...


class RunStore(Protocol):
    def add(self, run: Run) -> Run: ...
    def get(self, run_id: str) -> Run | None: ...
    def list_for_task(self, task_id: str) -> list[Run]: ...
    def update(self, run: Run) -> Run: ...
```

- [ ] **Step 2: Verify it imports, commit**

```bash
uv run python -c "import domain.ports" && git add -A && git commit -m "feat: store ports (protocols) for project/work-item/team/run"
```

---

### Task 7: SQLAlchemy tables + Project/WorkItem stores

**Files:**
- Create: `src/adapters/database/tables.py`, `src/adapters/database/engine.py`, `src/adapters/database/stores.py`
- Test: `tests/unit/test_stores.py`

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_stores.py`)

```python
import pytest

from adapters.database.engine import make_engine, make_session_factory
from adapters.database.stores import SqlProjectStore, SqlWorkItemStore
from adapters.database.tables import metadata
from domain.models import Project, WorkItem, WorkItemKind, WorkItemStatus


@pytest.fixture()
def session_factory():
    engine = make_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    return make_session_factory(engine)


def test_project_roundtrip_and_owner_scoping(session_factory):
    store = SqlProjectStore(session_factory)
    p = store.add(Project(owner_id="u1", name="llm_api", repo_url="https://github.com/x/y"))
    assert store.get(p.id, owner_id="u1").name == "llm_api"
    assert store.get(p.id, owner_id="someone-else") is None
    assert [x.id for x in store.list("u1")] == [p.id]


def test_project_update_and_delete(session_factory):
    store = SqlProjectStore(session_factory)
    p = store.add(Project(owner_id="u1", name="a", repo_url="r"))
    p = p.model_copy(update={"name": "b"})
    assert store.update(p).name == "b"
    assert store.delete(p.id, owner_id="u1") is True
    assert store.get(p.id, owner_id="u1") is None


def test_work_item_filters(session_factory):
    store = SqlWorkItemStore(session_factory)
    epic = store.add(WorkItem(project_id="p1", kind=WorkItemKind.EPIC, title="E"))
    task = store.add(
        WorkItem(
            project_id="p1",
            kind=WorkItemKind.TASK,
            parent_id=epic.id,
            title="T",
            status=WorkItemStatus.READY,
        )
    )
    assert [i.id for i in store.list("p1", kind=WorkItemKind.TASK)] == [task.id]
    assert [i.id for i in store.list("p1", status=WorkItemStatus.READY)] == [task.id]
    assert [i.id for i in store.list("p1", parent_id=epic.id)] == [task.id]
    assert len(store.list("p1")) == 2
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_stores.py -v` — Expected: FAIL (ImportError).

- [ ] **Step 3: Implement tables** (`src/adapters/database/tables.py`)

```python
from sqlalchemy import JSON, Column, DateTime, Float, MetaData, String, Table, Text

metadata = MetaData()

projects = Table(
    "projects",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("owner_id", String(64), nullable=False, index=True),
    Column("name", String(200), nullable=False),
    Column("repo_url", String(500)),
    Column("local_path", String(500)),
    Column("team_id", String(32)),
    Column("autonomy", String(20), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

work_items = Table(
    "work_items",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("project_id", String(32), nullable=False, index=True),
    Column("kind", String(10), nullable=False),
    Column("parent_id", String(32), index=True),
    Column("title", String(300), nullable=False),
    Column("body", Text, nullable=False, default=""),
    Column("acceptance_criteria", JSON, nullable=False),
    Column("status", String(20), nullable=False, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

teams = Table(
    "teams",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("owner_id", String(64), nullable=False, index=True),
    Column("name", String(200), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

agent_definitions = Table(
    "agent_definitions",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("team_id", String(32), nullable=False, index=True),
    Column("role", String(20), nullable=False),
    Column("name", String(100), nullable=False),
    Column("persona", Text, nullable=False, default=""),
    Column("model_alias", String(100), nullable=False),
    Column("runtime", String(50), nullable=False),
)

runs = Table(
    "runs",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("task_id", String(32), nullable=False, index=True),
    Column("team_id", String(32), nullable=False),
    Column("status", String(30), nullable=False, index=True),
    Column("stage", String(30)),
    Column("branch", String(200)),
    Column("pr_url", String(500)),
    Column("cost_usd", Float, nullable=False, default=0.0),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
```

- [ ] **Step 4: Implement engine helpers** (`src/adapters/database/engine.py`)

```python
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def make_engine(database_url: str) -> Engine:
    return create_engine(database_url)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
```

- [ ] **Step 5: Implement stores** (`src/adapters/database/stores.py`)

```python
from sqlalchemy import delete, insert, select, update
from sqlalchemy.orm import Session, sessionmaker

from adapters.database.tables import projects, work_items
from domain.models import Project, WorkItem, WorkItemKind, WorkItemStatus


class SqlProjectStore:
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sf = session_factory

    def add(self, project: Project) -> Project:
        with self._sf() as s, s.begin():
            s.execute(insert(projects).values(**project.model_dump()))
        return project

    def get(self, project_id: str, owner_id: str) -> Project | None:
        with self._sf() as s:
            row = s.execute(
                select(projects).where(projects.c.id == project_id, projects.c.owner_id == owner_id)
            ).mappings().first()
        return Project(**row) if row else None

    def list(self, owner_id: str, limit: int = 50, offset: int = 0) -> list[Project]:
        with self._sf() as s:
            rows = s.execute(
                select(projects)
                .where(projects.c.owner_id == owner_id)
                .order_by(projects.c.created_at.desc())
                .limit(limit)
                .offset(offset)
            ).mappings().all()
        return [Project(**r) for r in rows]

    def update(self, project: Project) -> Project:
        with self._sf() as s, s.begin():
            s.execute(update(projects).where(projects.c.id == project.id).values(**project.model_dump()))
        return project

    def delete(self, project_id: str, owner_id: str) -> bool:
        with self._sf() as s, s.begin():
            result = s.execute(
                delete(projects).where(projects.c.id == project_id, projects.c.owner_id == owner_id)
            )
        return result.rowcount > 0


class SqlWorkItemStore:
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sf = session_factory

    def add(self, item: WorkItem) -> WorkItem:
        with self._sf() as s, s.begin():
            s.execute(insert(work_items).values(**item.model_dump()))
        return item

    def get(self, item_id: str) -> WorkItem | None:
        with self._sf() as s:
            row = s.execute(select(work_items).where(work_items.c.id == item_id)).mappings().first()
        return WorkItem(**row) if row else None

    def list(
        self,
        project_id: str,
        kind: WorkItemKind | None = None,
        status: WorkItemStatus | None = None,
        parent_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[WorkItem]:
        stmt = select(work_items).where(work_items.c.project_id == project_id)
        if kind:
            stmt = stmt.where(work_items.c.kind == kind)
        if status:
            stmt = stmt.where(work_items.c.status == status)
        if parent_id:
            stmt = stmt.where(work_items.c.parent_id == parent_id)
        stmt = stmt.order_by(work_items.c.created_at).limit(limit).offset(offset)
        with self._sf() as s:
            rows = s.execute(stmt).mappings().all()
        return [WorkItem(**r) for r in rows]

    def update(self, item: WorkItem) -> WorkItem:
        with self._sf() as s, s.begin():
            s.execute(update(work_items).where(work_items.c.id == item.id).values(**item.model_dump()))
        return item

    def delete(self, item_id: str) -> bool:
        with self._sf() as s, s.begin():
            result = s.execute(delete(work_items).where(work_items.c.id == item_id))
        return result.rowcount > 0
```

- [ ] **Step 6: Run to verify pass**

Run: `uv run pytest tests/unit/test_stores.py -v` — Expected: 3 PASS.

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat: sqlalchemy tables + project/work-item stores"
```

---

### Task 8: Team and Run stores

**Files:**
- Modify: `src/adapters/database/stores.py` (append)
- Test: `tests/unit/test_stores_teams_runs.py`

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_stores_teams_runs.py`)

```python
import pytest

from adapters.database.engine import make_engine, make_session_factory
from adapters.database.stores import SqlRunStore, SqlTeamStore
from adapters.database.tables import metadata
from domain.models import Run, RunStatus
from domain.teams import default_team


@pytest.fixture()
def session_factory():
    engine = make_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    return make_session_factory(engine)


def test_team_roundtrip_with_agents(session_factory):
    store = SqlTeamStore(session_factory)
    team, agents = default_team(owner_id="u1")
    store.add(team, agents)
    assert store.get(team.id, owner_id="u1").name == "Default Team"
    assert store.get(team.id, owner_id="u2") is None
    assert [a.role for a in store.agents(team.id)] == [a.role for a in agents]
    assert [t.id for t in store.list("u1")] == [team.id]


def test_run_roundtrip_and_update(session_factory):
    store = SqlRunStore(session_factory)
    r = store.add(Run(task_id="t1", team_id="tm1"))
    r = r.model_copy(update={"status": RunStatus.RUNNING, "stage": "plan"})
    store.update(r)
    assert store.get(r.id).status == RunStatus.RUNNING
    assert [x.id for x in store.list_for_task("t1")] == [r.id]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_stores_teams_runs.py -v` — Expected: FAIL (ImportError).

- [ ] **Step 3: Append to `src/adapters/database/stores.py`**

```python
from adapters.database.tables import agent_definitions, runs, teams
from domain.models import AgentDefinition, Run, Team


class SqlTeamStore:
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sf = session_factory

    def add(self, team: Team, agents: list[AgentDefinition]) -> Team:
        with self._sf() as s, s.begin():
            s.execute(insert(teams).values(**team.model_dump()))
            for agent in agents:
                s.execute(insert(agent_definitions).values(**agent.model_dump()))
        return team

    def get(self, team_id: str, owner_id: str) -> Team | None:
        with self._sf() as s:
            row = s.execute(
                select(teams).where(teams.c.id == team_id, teams.c.owner_id == owner_id)
            ).mappings().first()
        return Team(**row) if row else None

    def list(self, owner_id: str) -> list[Team]:
        with self._sf() as s:
            rows = s.execute(select(teams).where(teams.c.owner_id == owner_id)).mappings().all()
        return [Team(**r) for r in rows]

    def agents(self, team_id: str) -> list[AgentDefinition]:
        with self._sf() as s:
            rows = s.execute(
                select(agent_definitions).where(agent_definitions.c.team_id == team_id)
            ).mappings().all()
        return [AgentDefinition(**r) for r in rows]


class SqlRunStore:
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sf = session_factory

    def add(self, run: Run) -> Run:
        with self._sf() as s, s.begin():
            s.execute(insert(runs).values(**run.model_dump()))
        return run

    def get(self, run_id: str) -> Run | None:
        with self._sf() as s:
            row = s.execute(select(runs).where(runs.c.id == run_id)).mappings().first()
        return Run(**row) if row else None

    def list_for_task(self, task_id: str) -> list[Run]:
        with self._sf() as s:
            rows = s.execute(
                select(runs).where(runs.c.task_id == task_id).order_by(runs.c.created_at.desc())
            ).mappings().all()
        return [Run(**r) for r in rows]

    def update(self, run: Run) -> Run:
        with self._sf() as s, s.begin():
            s.execute(update(runs).where(runs.c.id == run.id).values(**run.model_dump()))
        return run
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/unit/test_stores_teams_runs.py -v` — Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: team and run stores"
```

---

### Task 9: FastAPI app factory, envelope, error handling, auth dependency

**Files:**
- Create: `src/interactors/api/app.py`, `src/interactors/api/envelope.py`, `src/interactors/api/auth.py`, `src/interactors/api/deps.py`
- Test: `tests/integration/test_app.py`

- [ ] **Step 1: Write the failing tests** (`tests/integration/test_app.py`)

```python
from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def make_client() -> TestClient:
    app = create_app(Settings(_env_file=None, database_url="sqlite:///:memory:"))
    return TestClient(app)


def test_health():
    resp = make_client().get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"success": True, "data": {"status": "ok"}, "error": None}


def test_unknown_route_envelope():
    resp = make_client().get("/nope")
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["error"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/integration/test_app.py -v` — Expected: FAIL (ImportError).

- [ ] **Step 3: Implement envelope** (`src/interactors/api/envelope.py`)

```python
from typing import Any


def ok(data: Any, meta: dict | None = None) -> dict:
    body: dict = {"success": True, "data": data, "error": None}
    if meta:
        body["meta"] = meta
    return body


def err(message: str) -> dict:
    return {"success": False, "data": None, "error": message}
```

- [ ] **Step 4: Implement auth** (`src/interactors/api/auth.py`)

```python
from fastapi import HTTPException, Request

DEV_USER_ID = "dev-user"


def current_user_id(request: Request) -> str:
    """Dev mode: fixed local user. Auth0 JWT validation replaces this in remote profile (later plan)."""
    settings = request.app.state.settings
    if settings.auth_mode == "dev":
        return DEV_USER_ID
    raise HTTPException(status_code=501, detail="auth0 mode not implemented yet")
```

- [ ] **Step 5: Implement deps + app factory** (`src/interactors/api/deps.py`)

```python
from fastapi import Request

from adapters.database.stores import SqlProjectStore, SqlRunStore, SqlTeamStore, SqlWorkItemStore


def project_store(request: Request) -> SqlProjectStore:
    return SqlProjectStore(request.app.state.session_factory)


def work_item_store(request: Request) -> SqlWorkItemStore:
    return SqlWorkItemStore(request.app.state.session_factory)


def team_store(request: Request) -> SqlTeamStore:
    return SqlTeamStore(request.app.state.session_factory)


def run_store(request: Request) -> SqlRunStore:
    return SqlRunStore(request.app.state.session_factory)
```

(`src/interactors/api/app.py`)

```python
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware

from adapters.database.engine import make_engine, make_session_factory
from adapters.database.tables import metadata
from interactors.api.envelope import err, ok
from interactors.api.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="yaah")
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )

    engine = make_engine(settings.database_url)
    metadata.create_all(engine)  # alembic replaces this once the schema stabilises
    app.state.settings = settings
    app.state.session_factory = make_session_factory(engine)

    # Starlette base class so unknown-route 404s are enveloped too (fastapi.HTTPException subclasses it)
    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=err(str(exc.detail)))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content=err(str(exc.errors())))

    @app.get("/health")
    def health() -> dict:
        return ok({"status": "ok"})

    from interactors.api.routes import projects, runs, teams, work_items

    app.include_router(projects.router)
    app.include_router(work_items.router)
    app.include_router(teams.router)
    app.include_router(runs.router)
    return app
```

Create empty routers so the app imports (`src/interactors/api/routes/projects.py`, `work_items.py`, `teams.py`, `runs.py` — each starts as):

```python
from fastapi import APIRouter

router = APIRouter()
```

- [ ] **Step 6: Run to verify pass**

Run: `uv run pytest tests/integration/test_app.py -v` — Expected: 2 PASS.

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat: fastapi app factory with envelope, error handlers, dev auth"
```

---

### Task 10: Projects routes

**Files:**
- Modify: `src/interactors/api/routes/projects.py`
- Test: `tests/integration/test_projects_api.py`

- [ ] **Step 1: Write the failing tests** (`tests/integration/test_projects_api.py`)

```python
from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def make_client() -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, database_url="sqlite:///:memory:")))


def test_create_get_list_update_delete_project():
    c = make_client()
    created = c.post(
        "/projects", json={"name": "llm_api", "repo_url": "https://github.com/x/llm_api"}
    )
    assert created.status_code == 201
    pid = created.json()["data"]["id"]
    assert created.json()["data"]["owner_id"] == "dev-user"

    assert c.get(f"/projects/{pid}").json()["data"]["name"] == "llm_api"
    assert len(c.get("/projects").json()["data"]) == 1

    updated = c.patch(f"/projects/{pid}", json={"autonomy": "gated_merge"})
    assert updated.json()["data"]["autonomy"] == "gated_merge"

    assert c.delete(f"/projects/{pid}").status_code == 200
    assert c.get(f"/projects/{pid}").status_code == 404


def test_create_project_requires_a_repo():
    resp = make_client().post("/projects", json={"name": "nowhere"})
    assert resp.status_code == 422
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/integration/test_projects_api.py -v` — Expected: FAIL (404s — routes don't exist).

- [ ] **Step 3: Implement** (`src/interactors/api/routes/projects.py`)

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from adapters.database.stores import SqlProjectStore
from domain.models import AutonomyLevel, Project
from interactors.api.auth import current_user_id
from interactors.api.deps import project_store
from interactors.api.envelope import ok

router = APIRouter(prefix="/projects", tags=["projects"])


class CreateProject(BaseModel):
    name: str
    repo_url: str | None = None
    local_path: str | None = None
    autonomy: AutonomyLevel = AutonomyLevel.GATED_ALL


class UpdateProject(BaseModel):
    name: str | None = None
    team_id: str | None = None
    autonomy: AutonomyLevel | None = None


@router.post("", status_code=201)
def create(
    body: CreateProject,
    user_id: str = Depends(current_user_id),
    store: SqlProjectStore = Depends(project_store),
) -> dict:
    try:
        project = Project(owner_id=user_id, **body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ok(store.add(project).model_dump(mode="json"))


@router.get("")
def list_projects(
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(current_user_id),
    store: SqlProjectStore = Depends(project_store),
) -> dict:
    items = store.list(user_id, limit=limit, offset=offset)
    return ok([p.model_dump(mode="json") for p in items], meta={"limit": limit, "offset": offset})


def _get_or_404(store: SqlProjectStore, project_id: str, user_id: str) -> Project:
    project = store.get(project_id, owner_id=user_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    return project


@router.get("/{project_id}")
def get(
    project_id: str,
    user_id: str = Depends(current_user_id),
    store: SqlProjectStore = Depends(project_store),
) -> dict:
    return ok(_get_or_404(store, project_id, user_id).model_dump(mode="json"))


@router.patch("/{project_id}")
def patch(
    project_id: str,
    body: UpdateProject,
    user_id: str = Depends(current_user_id),
    store: SqlProjectStore = Depends(project_store),
) -> dict:
    project = _get_or_404(store, project_id, user_id)
    updated = project.model_copy(update=body.model_dump(exclude_none=True))
    return ok(store.update(updated).model_dump(mode="json"))


@router.delete("/{project_id}")
def delete(
    project_id: str,
    user_id: str = Depends(current_user_id),
    store: SqlProjectStore = Depends(project_store),
) -> dict:
    _get_or_404(store, project_id, user_id)
    store.delete(project_id, owner_id=user_id)
    return ok({"deleted": project_id})
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/integration/test_projects_api.py -v` — Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: projects CRUD API"
```

---

### Task 11: Work-items routes (CRUD + status transition)

**Files:**
- Modify: `src/interactors/api/routes/work_items.py`
- Test: `tests/integration/test_work_items_api.py`

- [ ] **Step 1: Write the failing tests** (`tests/integration/test_work_items_api.py`)

```python
from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def make_client() -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, database_url="sqlite:///:memory:")))


def _project(c: TestClient) -> str:
    return c.post("/projects", json={"name": "p", "repo_url": "r"}).json()["data"]["id"]


def test_epic_feature_task_hierarchy_and_filters():
    c = make_client()
    pid = _project(c)
    epic = c.post(
        f"/projects/{pid}/work-items", json={"kind": "epic", "title": "Harness"}
    ).json()["data"]
    feature = c.post(
        f"/projects/{pid}/work-items",
        json={"kind": "feature", "title": "Board", "parent_id": epic["id"]},
    ).json()["data"]
    task = c.post(
        f"/projects/{pid}/work-items",
        json={
            "kind": "task",
            "title": "Kanban columns",
            "parent_id": feature["id"],
            "acceptance_criteria": ["columns render", "drag updates status"],
        },
    ).json()["data"]
    assert task["status"] == "draft"

    tasks = c.get(f"/projects/{pid}/work-items", params={"kind": "task"}).json()["data"]
    assert [t["id"] for t in tasks] == [task["id"]]
    children = c.get(f"/projects/{pid}/work-items", params={"parent_id": feature["id"]}).json()["data"]
    assert [t["id"] for t in children] == [task["id"]]


def test_task_without_parent_rejected():
    c = make_client()
    pid = _project(c)
    resp = c.post(f"/projects/{pid}/work-items", json={"kind": "task", "title": "orphan"})
    assert resp.status_code == 422


def test_status_transition_enforced():
    c = make_client()
    pid = _project(c)
    epic = c.post(f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E"}).json()["data"]
    ok_resp = c.post(f"/work-items/{epic['id']}/status", json={"status": "ready"})
    assert ok_resp.json()["data"]["status"] == "ready"
    bad = c.post(f"/work-items/{epic['id']}/status", json={"status": "done"})
    assert bad.status_code == 409


def test_update_and_delete_work_item():
    c = make_client()
    pid = _project(c)
    epic = c.post(f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E"}).json()["data"]
    patched = c.patch(f"/work-items/{epic['id']}", json={"title": "E2", "body": "details"})
    assert patched.json()["data"]["title"] == "E2"
    assert c.delete(f"/work-items/{epic['id']}").status_code == 200
    assert c.patch(f"/work-items/{epic['id']}", json={"title": "x"}).status_code == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/integration/test_work_items_api.py -v` — Expected: FAIL (404s).

- [ ] **Step 3: Implement** (`src/interactors/api/routes/work_items.py`)

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from adapters.database.stores import SqlProjectStore, SqlWorkItemStore
from domain.models import WorkItem, WorkItemKind, WorkItemStatus, utc_now
from domain.transitions import InvalidTransition, validate_transition
from interactors.api.auth import current_user_id
from interactors.api.deps import project_store, work_item_store
from interactors.api.envelope import ok

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
def create(
    project_id: str,
    body: CreateWorkItem,
    user_id: str = Depends(current_user_id),
    projects: SqlProjectStore = Depends(project_store),
    store: SqlWorkItemStore = Depends(work_item_store),
) -> dict:
    if not projects.get(project_id, owner_id=user_id):
        raise HTTPException(status_code=404, detail="project not found")
    try:
        item = WorkItem(project_id=project_id, **body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ok(store.add(item).model_dump(mode="json"))


@router.get("/projects/{project_id}/work-items")
def list_items(
    project_id: str,
    kind: WorkItemKind | None = None,
    status: WorkItemStatus | None = None,
    parent_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    user_id: str = Depends(current_user_id),
    projects: SqlProjectStore = Depends(project_store),
    store: SqlWorkItemStore = Depends(work_item_store),
) -> dict:
    if not projects.get(project_id, owner_id=user_id):
        raise HTTPException(status_code=404, detail="project not found")
    items = store.list(project_id, kind=kind, status=status, parent_id=parent_id, limit=limit, offset=offset)
    return ok([i.model_dump(mode="json") for i in items], meta={"limit": limit, "offset": offset})


def _get_or_404(store: SqlWorkItemStore, item_id: str) -> WorkItem:
    item = store.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="work item not found")
    return item


@router.patch("/work-items/{item_id}")
def patch(
    item_id: str,
    body: UpdateWorkItem,
    store: SqlWorkItemStore = Depends(work_item_store),
) -> dict:
    item = _get_or_404(store, item_id)
    updated = item.model_copy(update={**body.model_dump(exclude_none=True), "updated_at": utc_now()})
    return ok(store.update(updated).model_dump(mode="json"))


@router.post("/work-items/{item_id}/status")
def set_status(
    item_id: str,
    body: SetStatus,
    store: SqlWorkItemStore = Depends(work_item_store),
) -> dict:
    item = _get_or_404(store, item_id)
    try:
        validate_transition(item.status, body.status)
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    updated = item.model_copy(update={"status": body.status, "updated_at": utc_now()})
    return ok(store.update(updated).model_dump(mode="json"))


@router.delete("/work-items/{item_id}")
def delete(item_id: str, store: SqlWorkItemStore = Depends(work_item_store)) -> dict:
    _get_or_404(store, item_id)
    store.delete(item_id)
    return ok({"deleted": item_id})
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/integration/test_work_items_api.py -v` — Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: work-items CRUD + status transition API"
```

---

### Task 12: Teams routes (incl. default team)

**Files:**
- Modify: `src/interactors/api/routes/teams.py`
- Test: `tests/integration/test_teams_api.py`

- [ ] **Step 1: Write the failing tests** (`tests/integration/test_teams_api.py`)

```python
from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def make_client() -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, database_url="sqlite:///:memory:")))


def test_create_default_team_and_fetch_agents():
    c = make_client()
    created = c.post("/teams/default")
    assert created.status_code == 201
    team = created.json()["data"]["team"]
    agents = created.json()["data"]["agents"]
    assert [a["role"] for a in agents] == ["lead", "backend", "qa"]

    assert c.get("/teams").json()["data"][0]["id"] == team["id"]
    fetched = c.get(f"/teams/{team['id']}").json()["data"]
    assert [a["role"] for a in fetched["agents"]] == ["lead", "backend", "qa"]


def test_get_missing_team_404():
    assert make_client().get("/teams/nope").status_code == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/integration/test_teams_api.py -v` — Expected: FAIL (404/405).

- [ ] **Step 3: Implement** (`src/interactors/api/routes/teams.py`)

```python
from fastapi import APIRouter, Depends, HTTPException

from adapters.database.stores import SqlTeamStore
from domain.teams import default_team
from interactors.api.auth import current_user_id
from interactors.api.deps import team_store
from interactors.api.envelope import ok

router = APIRouter(prefix="/teams", tags=["teams"])


@router.post("/default", status_code=201)
def create_default(
    user_id: str = Depends(current_user_id),
    store: SqlTeamStore = Depends(team_store),
) -> dict:
    team, agents = default_team(owner_id=user_id)
    store.add(team, agents)
    return ok(
        {
            "team": team.model_dump(mode="json"),
            "agents": [a.model_dump(mode="json") for a in agents],
        }
    )


@router.get("")
def list_teams(
    user_id: str = Depends(current_user_id),
    store: SqlTeamStore = Depends(team_store),
) -> dict:
    return ok([t.model_dump(mode="json") for t in store.list(user_id)])


@router.get("/{team_id}")
def get(
    team_id: str,
    user_id: str = Depends(current_user_id),
    store: SqlTeamStore = Depends(team_store),
) -> dict:
    team = store.get(team_id, owner_id=user_id)
    if not team:
        raise HTTPException(status_code=404, detail="team not found")
    agents = store.agents(team_id)
    return ok(
        {
            **team.model_dump(mode="json"),
            "agents": [a.model_dump(mode="json") for a in agents],
        }
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/integration/test_teams_api.py -v` — Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: teams API with default lead+engineer+qa team"
```

---

### Task 13: Runs routes (create pending, list, get)

**Files:**
- Modify: `src/interactors/api/routes/runs.py`
- Test: `tests/integration/test_runs_api.py`

The A3 plan replaces "create pending run" with "start Temporal workflow"; the API contract stays the same.

- [ ] **Step 1: Write the failing tests** (`tests/integration/test_runs_api.py`)

```python
from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def make_client() -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, database_url="sqlite:///:memory:")))


def _ready_task(c: TestClient) -> tuple[str, str]:
    pid = c.post("/projects", json={"name": "p", "repo_url": "r"}).json()["data"]["id"]
    team_id = c.post("/teams/default").json()["data"]["team"]["id"]
    c.patch(f"/projects/{pid}", json={"team_id": team_id})
    epic = c.post(f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E"}).json()["data"]
    feat = c.post(
        f"/projects/{pid}/work-items",
        json={"kind": "feature", "title": "F", "parent_id": epic["id"]},
    ).json()["data"]
    task = c.post(
        f"/projects/{pid}/work-items",
        json={"kind": "task", "title": "T", "parent_id": feat["id"]},
    ).json()["data"]
    c.post(f"/work-items/{task['id']}/status", json={"status": "ready"})
    return task["id"], team_id


def test_start_run_on_ready_task():
    c = make_client()
    task_id, team_id = _ready_task(c)
    resp = c.post(f"/work-items/{task_id}/runs")
    assert resp.status_code == 201
    run = resp.json()["data"]
    assert run["status"] == "pending"
    assert run["team_id"] == team_id
    # task moved to in_progress
    runs = c.get(f"/work-items/{task_id}/runs").json()["data"]
    assert [r["id"] for r in runs] == [run["id"]]
    assert c.get(f"/runs/{run['id']}").json()["data"]["id"] == run["id"]


def test_run_rejected_unless_task_ready():
    c = make_client()
    task_id, _ = _ready_task(c)
    c.post(f"/work-items/{task_id}/runs")  # consumes ready -> in_progress
    again = c.post(f"/work-items/{task_id}/runs")
    assert again.status_code == 409
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/integration/test_runs_api.py -v` — Expected: FAIL (404/405).

- [ ] **Step 3: Implement** (`src/interactors/api/routes/runs.py`)

```python
from fastapi import APIRouter, Depends, HTTPException

from adapters.database.stores import SqlProjectStore, SqlRunStore, SqlWorkItemStore
from domain.models import Run, WorkItemKind, WorkItemStatus, utc_now
from interactors.api.auth import current_user_id
from interactors.api.deps import project_store, run_store, work_item_store
from interactors.api.envelope import ok

router = APIRouter(tags=["runs"])


@router.post("/work-items/{task_id}/runs", status_code=201)
def start_run(
    task_id: str,
    user_id: str = Depends(current_user_id),
    items: SqlWorkItemStore = Depends(work_item_store),
    projects: SqlProjectStore = Depends(project_store),
    store: SqlRunStore = Depends(run_store),
) -> dict:
    task = items.get(task_id)
    if not task or task.kind != WorkItemKind.TASK:
        raise HTTPException(status_code=404, detail="task not found")
    if task.status != WorkItemStatus.READY:
        raise HTTPException(status_code=409, detail=f"task is {task.status}, must be ready")
    project = projects.get(task.project_id, owner_id=user_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    if not project.team_id:
        raise HTTPException(status_code=409, detail="project has no team assigned")

    run = store.add(Run(task_id=task_id, team_id=project.team_id))
    items.update(
        task.model_copy(update={"status": WorkItemStatus.IN_PROGRESS, "updated_at": utc_now()})
    )
    return ok(run.model_dump(mode="json"))


@router.get("/work-items/{task_id}/runs")
def list_runs(task_id: str, store: SqlRunStore = Depends(run_store)) -> dict:
    return ok([r.model_dump(mode="json") for r in store.list_for_task(task_id)])


@router.get("/runs/{run_id}")
def get_run(run_id: str, store: SqlRunStore = Depends(run_store)) -> dict:
    run = store.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return ok(run.model_dump(mode="json"))
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/integration/test_runs_api.py -v` — Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: runs API (pending run creation, listing, fetch)"
```

---

### Task 14: Makefile, coverage check, final verification

**Files:**
- Create: `Makefile`

- [ ] **Step 1: Write `Makefile`**

```makefile
.PHONY: dev test coverage lint up

up:
	docker compose up -d postgres

dev:
	uv run uvicorn --app-dir src interactors.api.app:create_app --factory --reload

test:
	uv run pytest

coverage:
	uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80

lint:
	uv run ruff check src tests
```

- [ ] **Step 2: Run the full suite + coverage**

Run: `make coverage` — Expected: all tests PASS, coverage ≥ 80%.

- [ ] **Step 3: Run lint, fix anything trivial**

Run: `make lint` — Expected: clean (or fix reported issues and rerun).

- [ ] **Step 4: Smoke-test the live API against Postgres**

```bash
docker compose up -d postgres
uv run uvicorn --app-dir src interactors.api.app:create_app --factory --port 8100 &
sleep 2 && curl -s localhost:8100/health
kill %1
```
Expected: `{"success":true,"data":{"status":"ok"},"error":null}`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "chore: makefile, coverage gate, live smoke check"
```

---

## Deferred to later plans (do not build now)

- **A2**: React board UI. **A3**: Temporal workflow replacing the pending-run stub; SSE run events. **A4**: sandbox/proxy/GitHub App; `WorkspaceProvider` adapters. **A5**: Claude Code `AgentRuntime` adapter + LiteLLM. **A6**: refinement chat, memory, Auth0 for remote profile, alembic migration baseline (replace `create_all`).
