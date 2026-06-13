# A3 Temporal Run Pipeline + FakeAgentRuntime — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a `pending` run into a durable Temporal workflow that drives the 6-stage pipeline (PLAN→PROVISION→IMPLEMENT→VERIFY→PR→LEARN) with a scripted `FakeAgentRuntime`, human gates as signals, and an append-only event feed.

**Architecture:** Pure `domain/pipeline` policy + ports (`AgentRuntime`, `WorkspaceProvider`); Temporal is an adapter (`adapters/temporal/`); the workflow is the sole writer of run state via activities that use the existing UnitOfWork. The API starts the workflow and sends signals; A2's gate endpoints are refactored from direct DB writes to signal-senders.

**Tech Stack:** Python 3.12 · FastAPI · SQLAlchemy (sync) · **Temporal (`temporalio`)** · pytest + **pytest-asyncio** · `uv`.

**Spec:** `docs/specs/2026-06-12-a3-temporal-pipeline-design.md`

**Precondition:** A1/A1.5/A2 merged to `main` (run-write endpoints, UnitOfWork, repositories, envelope handlers, `domain/run_transitions.py`). Verify: `git log --oneline | grep -i 'run-status state machine'` returns a commit.

---

## Conventions for every task

- **TDD:** failing test → run red → minimal impl → run green → commit. Backend tests: `uv run pytest <path> -v`.
- **Commit format:** `<type>: <description>`.
- **Route style:** mirror `src/interactors/api/routes/work_items.py` (`uow: UnitOfWork = Depends(get_uow)`, `with uow.transaction():`, `return ok(...)`). Exception handlers already map `RecordNotFound`→404, `InvalidTransition`→409, `ValidationError`→422.
- **Immutability:** DTO updates via `model_copy(update={...})`.
- **Activity/workflow args are plain dicts/primitives** (avoid custom serialization); reconstruct DTOs inside activities.

## Suggested execution order (parallel waves)

- **Wave 1 (parallel worktrees):** Lane DOMAIN = T1→T2→T3→T4; Lane PERSIST = T7 (needs T1, so sequence T1 then fork); Lane INFRA = T14, T15. (T1 must land first; do it, then fork DOMAIN-rest / PERSIST / INFRA.)
- **Wave 2:** T5, T6 (need T3/T4); T8 (needs T14).
- **Wave 3:** T9 (needs T3,T5,T7), T12 (needs T8).
- **Wave 4:** T10 (needs T2,T9,T8), T13 (needs T7,T8,T12).
- **Wave 5:** T11 (needs T9,T10,T5,T6), then T16 (full verify).

Within a worktree, tasks are sequential. Lanes touch disjoint files (domain/ vs adapters/database/ vs infra) for clean merges.

---

## Task T1: Run pipeline enums + RunEvent DTO

**Files:**
- Modify: `src/domain/models.py`
- Test: `tests/unit/test_models.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_models.py`:
```python
def test_run_stage_and_event_types_exist():
    from domain.models import RunStage, RunEventType, RunEvent

    assert RunStage.PLAN == "plan"
    assert [s for s in RunStage] == [
        RunStage.PLAN, RunStage.PROVISION, RunStage.IMPLEMENT,
        RunStage.VERIFY, RunStage.PR, RunStage.LEARN,
    ]
    assert RunEventType.STAGE_STARTED == "stage_started"
    ev = RunEvent(run_id="r1", owner_id="dev-user", stage=RunStage.PLAN,
                  type=RunEventType.STAGE_STARTED, message="hi")
    assert ev.id and ev.created_at and ev.message == "hi"
```

- [ ] **Step 2: Run red**

Run: `uv run pytest tests/unit/test_models.py -k run_stage_and_event -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement** — add to `src/domain/models.py` (after `RunStatus`):
```python
class RunStage(StrEnum):
    PLAN = "plan"
    PROVISION = "provision"
    IMPLEMENT = "implement"
    VERIFY = "verify"
    PR = "pr"
    LEARN = "learn"


class RunEventType(StrEnum):
    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"
    AGENT_EVENT = "agent_event"
    GATE_OPENED = "gate_opened"
    GATE_RESOLVED = "gate_resolved"
    BLOCKED = "blocked"
    ERROR = "error"


class RunEvent(BaseModel):
    id: str = Field(default_factory=new_id)
    run_id: str
    owner_id: str
    stage: RunStage | None = None
    type: RunEventType
    message: str = ""
    created_at: datetime = Field(default_factory=utc_now)
```

- [ ] **Step 4: Run green**

Run: `uv run pytest tests/unit/test_models.py -k run_stage_and_event -v` → PASS.

- [ ] **Step 5: Commit**
```bash
git add src/domain/models.py tests/unit/test_models.py
git commit -m "feat: RunStage, RunEventType, RunEvent domain models"
```

---

## Task T2: Pure pipeline policy

**Files:**
- Create: `src/domain/pipeline.py`
- Test: `tests/unit/test_pipeline.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/unit/test_pipeline.py
from domain.models import AutonomyLevel, RunStage
from domain import pipeline


def test_stage_order():
    assert pipeline.STAGES == [
        RunStage.PLAN, RunStage.PROVISION, RunStage.IMPLEMENT,
        RunStage.VERIFY, RunStage.PR, RunStage.LEARN,
    ]


def test_gates_for_autonomy():
    assert pipeline.gates_for(AutonomyLevel.GATED_ALL) == {RunStage.PLAN, RunStage.PR}
    assert pipeline.gates_for(AutonomyLevel.GATED_MERGE) == {RunStage.PR}
    assert pipeline.gates_for(AutonomyLevel.FULL_AUTO) == set()


def test_verify_retry_policy():
    assert pipeline.VERIFY_MAX_LOOPS == 3
    assert pipeline.should_retry_verify(1) is True
    assert pipeline.should_retry_verify(3) is False
    assert pipeline.should_retry_verify(4) is False
```

- [ ] **Step 2: Run red** → `uv run pytest tests/unit/test_pipeline.py -v` (ModuleNotFound).

- [ ] **Step 3: Implement** `src/domain/pipeline.py`:
```python
from domain.models import AutonomyLevel, RunStage

STAGES: list[RunStage] = [
    RunStage.PLAN,
    RunStage.PROVISION,
    RunStage.IMPLEMENT,
    RunStage.VERIFY,
    RunStage.PR,
    RunStage.LEARN,
]

VERIFY_MAX_LOOPS = 3


def gates_for(autonomy: AutonomyLevel) -> set[RunStage]:
    if autonomy == AutonomyLevel.FULL_AUTO:
        return set()
    if autonomy == AutonomyLevel.GATED_MERGE:
        return {RunStage.PR}
    return {RunStage.PLAN, RunStage.PR}  # GATED_ALL


def should_retry_verify(loops_used: int) -> bool:
    return loops_used < VERIFY_MAX_LOOPS
```

- [ ] **Step 4: Run green** → PASS.

- [ ] **Step 5: Commit**
```bash
git add src/domain/pipeline.py tests/unit/test_pipeline.py
git commit -m "feat: pure pipeline policy (stages, gates, verify retry)"
```

---

## Task T3: AgentRuntime port + DTOs

**Files:**
- Create: `src/domain/runtime.py`
- Test: `tests/unit/test_runtime_dtos.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/unit/test_runtime_dtos.py
from domain.models import RunStage
from domain.runtime import AgentEvent, StageResult, RunContext


def test_runtime_dtos_construct():
    ctx = RunContext(run_id="r1", stage=RunStage.PLAN, task_title="T",
                     acceptance_criteria=["a"], workspace_path="/tmp/x")
    assert ctx.stage == RunStage.PLAN
    ev = AgentEvent(type="progress", stage=RunStage.PLAN, message="working")
    assert ev.type == "progress"
    res = StageResult(outcome="ok", cost_usd=0.5)
    assert res.outcome == "ok" and res.cost_usd == 0.5
```

- [ ] **Step 2: Run red** → ModuleNotFound.

- [ ] **Step 3: Implement** `src/domain/runtime.py`:
```python
from typing import Iterator, Literal, Protocol

from pydantic import BaseModel

from domain.models import RunStage


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
    acceptance_criteria: list[str] = []
    workspace_path: str
    prior_artifacts: dict = {}


class AgentRuntime(Protocol):
    def run_stage(self, ctx: RunContext) -> Iterator[AgentEvent]: ...
    def cancel(self, run_id: str) -> None: ...
```

- [ ] **Step 4: Run green** → PASS.

- [ ] **Step 5: Commit**
```bash
git add src/domain/runtime.py tests/unit/test_runtime_dtos.py
git commit -m "feat: AgentRuntime port + runtime DTOs"
```

---

## Task T4: WorkspaceProvider port

**Files:**
- Create: `src/domain/workspace.py`
- Test: `tests/unit/test_workspace_dto.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/unit/test_workspace_dto.py
from domain.workspace import Workspace


def test_workspace_dto():
    ws = Workspace(run_id="r1", path="/tmp/run-r1")
    assert ws.run_id == "r1" and ws.path == "/tmp/run-r1"
```

- [ ] **Step 2: Run red** → ModuleNotFound.

- [ ] **Step 3: Implement** `src/domain/workspace.py`:
```python
from typing import Protocol

from pydantic import BaseModel


class Workspace(BaseModel):
    run_id: str
    path: str


class WorkspaceProvider(Protocol):
    def provision(self, run_id: str) -> Workspace: ...
    def destroy(self, workspace: Workspace) -> None: ...
```

- [ ] **Step 4: Run green** → PASS.

- [ ] **Step 5: Commit**
```bash
git add src/domain/workspace.py tests/unit/test_workspace_dto.py
git commit -m "feat: WorkspaceProvider port + Workspace DTO"
```

---

## Task T5: FakeAgentRuntime

**Files:**
- Create: `src/adapters/runtime/__init__.py`, `src/adapters/runtime/fake.py`
- Test: `tests/unit/test_fake_runtime.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/unit/test_fake_runtime.py
from domain.models import RunStage
from domain.runtime import AgentEvent, RunContext, StageResult
from adapters.runtime.fake import FakeAgentRuntime, result_of


def _ctx(stage):
    return RunContext(run_id="r1", stage=stage, task_title="T",
                      acceptance_criteria=[], workspace_path="/tmp/x")


def test_default_script_succeeds_every_stage():
    rt = FakeAgentRuntime()
    events = list(rt.run_stage(_ctx(RunStage.PLAN)))
    assert events[-1].type == "result"
    assert result_of(events).outcome == "ok"


def test_scripted_failure():
    script = {RunStage.VERIFY: [AgentEvent(type="result", stage=RunStage.VERIFY,
              data=StageResult(outcome="fail").model_dump())]}
    rt = FakeAgentRuntime(script=script)
    assert result_of(list(rt.run_stage(_ctx(RunStage.VERIFY)))).outcome == "fail"
```

- [ ] **Step 2: Run red** → ModuleNotFound.

- [ ] **Step 3: Implement** `src/adapters/runtime/__init__.py` (empty) and `src/adapters/runtime/fake.py`:
```python
from typing import Iterator

from domain.models import RunStage
from domain.runtime import AgentEvent, RunContext, StageResult

_DEFAULT_COST = 0.25


def result_of(events: list[AgentEvent]) -> StageResult:
    """Extract the StageResult carried by the final 'result' event."""
    for event in reversed(events):
        if event.type == "result":
            return StageResult(**event.data)
    raise ValueError("no result event in stream")


def _default_events(stage: RunStage) -> list[AgentEvent]:
    return [
        AgentEvent(type="progress", stage=stage, message=f"{stage} starting"),
        AgentEvent(type="heartbeat", stage=stage, message="working"),
        AgentEvent(
            type="result",
            stage=stage,
            message=f"{stage} complete",
            data=StageResult(outcome="ok", cost_usd=_DEFAULT_COST).model_dump(),
        ),
    ]


class FakeAgentRuntime:
    """Replays a scripted event sequence per stage. Default: every stage 'ok'."""

    def __init__(self, script: dict[RunStage, list[AgentEvent]] | None = None):
        self._script = script or {}

    def run_stage(self, ctx: RunContext) -> Iterator[AgentEvent]:
        events = self._script.get(ctx.stage) or _default_events(ctx.stage)
        for event in events:
            yield event

    def cancel(self, run_id: str) -> None:  # no-op for the fake
        return None
```

- [ ] **Step 4: Run green** → PASS.

- [ ] **Step 5: Commit**
```bash
git add src/adapters/runtime tests/unit/test_fake_runtime.py
git commit -m "feat: FakeAgentRuntime (scripted event replay)"
```

---

## Task T6: LocalTempWorkspace

**Files:**
- Create: `src/adapters/workspace/__init__.py`, `src/adapters/workspace/local.py`
- Test: `tests/unit/test_local_workspace.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/unit/test_local_workspace.py
import os

from adapters.workspace.local import LocalTempWorkspace


def test_provision_creates_dir_and_destroy_removes_it():
    provider = LocalTempWorkspace()
    ws = provider.provision("r1")
    assert os.path.isdir(ws.path)
    provider.destroy(ws)
    assert not os.path.exists(ws.path)
```

- [ ] **Step 2: Run red** → ModuleNotFound.

- [ ] **Step 3: Implement** `src/adapters/workspace/__init__.py` (empty) and `src/adapters/workspace/local.py`:
```python
import shutil
import tempfile

from domain.workspace import Workspace


class LocalTempWorkspace:
    """A3 stub: a throwaway temp directory per run (no real git/clone)."""

    def provision(self, run_id: str) -> Workspace:
        path = tempfile.mkdtemp(prefix=f"yaah-run-{run_id}-")
        return Workspace(run_id=run_id, path=path)

    def destroy(self, workspace: Workspace) -> None:
        shutil.rmtree(workspace.path, ignore_errors=True)
```

- [ ] **Step 4: Run green** → PASS.

- [ ] **Step 5: Commit**
```bash
git add src/adapters/workspace tests/unit/test_local_workspace.py
git commit -m "feat: LocalTempWorkspace provider"
```

---

## Task T7: run_events persistence (ORM, repo, UoW, port)

**Files:**
- Modify: `src/adapters/database/orm.py`, `src/adapters/database/repositories.py`, `src/adapters/database/uow.py`, `src/adapters/database/ports.py`
- Test: `tests/unit/test_run_events_repo.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/unit/test_run_events_repo.py
from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.models import RunEvent, RunEventType, RunStage


def _uow():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return SqlUnitOfWork(make_session_factory(engine), required_filters={"owner_id": "u1"})


def test_create_and_list_run_events_owner_scoped():
    uow = _uow()
    with uow.transaction():
        uow.run_events.create(RunEvent(run_id="r1", owner_id="u1", stage=RunStage.PLAN,
                                       type=RunEventType.STAGE_STARTED, message="a"))
        uow.run_events.create(RunEvent(run_id="r1", owner_id="u1", stage=RunStage.PLAN,
                                       type=RunEventType.STAGE_COMPLETED, message="b"))
        page = uow.run_events.list(filters={"run_id": "r1"}, order_by="created_at")
    assert page.total == 2
    assert [e.type for e in page.results] == ["stage_started", "stage_completed"]


def test_run_events_cross_tenant_hidden():
    uow = _uow()
    with uow.transaction():
        uow.run_events.create(RunEvent(run_id="r1", owner_id="u1", type=RunEventType.AGENT_EVENT))
    other = SqlUnitOfWork(uow._session_factory, required_filters={"owner_id": "u2"})
    with other.transaction():
        page = other.run_events.list(filters={"run_id": "r1"})
    assert page.total == 0
```

- [ ] **Step 2: Run red** → `uv run pytest tests/unit/test_run_events_repo.py -v` (AttributeError: no `run_events`).

- [ ] **Step 3: Implement**

Add to `src/adapters/database/orm.py` (after `RunRow`; reuse existing imports `String, DateTime, Text`):
```python
class RunEventRow(Base):
    __tablename__ = "run_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    stage: Mapped[str | None] = mapped_column(String(30))
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

Add to `src/adapters/database/repositories.py`:
```python
from adapters.database.orm import RunEventRow  # add to existing import block
from domain.models import RunEvent            # add to existing import block


class RunEventRepository(SqlRepository[RunEvent]):
    orm_model = RunEventRow
    dto = RunEvent
    default_order_by = "created_at"
```

Add to `src/adapters/database/uow.py` (import `RunEventRepository`, add property):
```python
    @property
    def run_events(self) -> RunEventRepository:
        return RunEventRepository(self.session, self._required_filters)
```

Add to `src/adapters/database/ports.py` `UnitOfWork` Protocol (import `RunEvent`):
```python
    @property
    def run_events(self) -> Repository[RunEvent]: ...
```

- [ ] **Step 4: Run green** → PASS.

- [ ] **Step 5: Commit**
```bash
git add src/adapters/database tests/unit/test_run_events_repo.py
git commit -m "feat: run_events table, repository, and UoW property"
```

---

## Task T8: Temporal config + client

**Files:**
- Create: `src/adapters/temporal/__init__.py`, `src/adapters/temporal/config.py`, `src/adapters/temporal/client.py`
- Modify: `src/interactors/api/settings.py`
- Test: `tests/unit/test_temporal_config.py`

> Depends on T14 (temporalio installed).

- [ ] **Step 1: Write the failing test**
```python
# tests/unit/test_temporal_config.py
from interactors.api.settings import Settings
from adapters.temporal.config import TemporalConfig


def test_temporal_config_from_settings_defaults():
    cfg = TemporalConfig.from_settings(Settings(_env_file=None))
    assert cfg.address == "localhost:7233"
    assert cfg.namespace == "default"
    assert cfg.task_queue == "yaah-runs"
```

- [ ] **Step 2: Run red** → ImportError.

- [ ] **Step 3: Implement**

Add to `src/interactors/api/settings.py` (new fields on `Settings`):
```python
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    task_queue: str = "yaah-runs"
```

`src/adapters/temporal/__init__.py` (empty). `src/adapters/temporal/config.py`:
```python
from dataclasses import dataclass


@dataclass(frozen=True)
class TemporalConfig:
    address: str
    namespace: str
    task_queue: str

    @classmethod
    def from_settings(cls, settings) -> "TemporalConfig":
        return cls(
            address=settings.temporal_address,
            namespace=settings.temporal_namespace,
            task_queue=settings.task_queue,
        )
```

`src/adapters/temporal/client.py` — a sync wrapper the FastAPI routes use. It connects per call (fine for A3 volume) and runs the async client in a fresh event loop:
```python
import asyncio

from temporalio.client import Client

from adapters.temporal.config import TemporalConfig


class TemporalRunClient:
    """Sync facade over the async Temporal client for the sync FastAPI layer."""

    def __init__(self, config: TemporalConfig):
        self._config = config

    def _run(self, coro):
        return asyncio.run(coro)

    async def _client(self) -> Client:
        return await Client.connect(self._config.address, namespace=self._config.namespace)

    def start_run_workflow(self, run_input: dict) -> None:
        async def _go():
            client = await self._client()
            await client.start_workflow(
                "RunWorkflow",
                run_input,
                id=run_input["run_id"],
                task_queue=self._config.task_queue,
            )
        self._run(_go())

    def signal(self, run_id: str, name: str) -> None:
        async def _go():
            client = await self._client()
            handle = client.get_workflow_handle(run_id)
            await handle.signal(name)
        self._run(_go())
```

- [ ] **Step 4: Run green** → `uv run pytest tests/unit/test_temporal_config.py -v` PASS.

- [ ] **Step 5: Commit**
```bash
git add src/adapters/temporal/__init__.py src/adapters/temporal/config.py src/adapters/temporal/client.py src/interactors/api/settings.py tests/unit/test_temporal_config.py
git commit -m "feat: Temporal config + sync client facade + settings"
```

---

## Task T9: Temporal activities

**Files:**
- Create: `src/adapters/temporal/activities.py`
- Test: `tests/unit/test_activities.py`

> Depends on T3 (runtime), T5 (FakeAgentRuntime), T6 (workspace), T7 (run_events).

- [ ] **Step 1: Write the failing test** — activities are plain methods callable without a Temporal server:
```python
# tests/unit/test_activities.py
from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from adapters.runtime.fake import FakeAgentRuntime
from adapters.temporal.activities import RunActivities
from domain.models import Run, RunStage, RunStatus


def _factory():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def _seed_run(factory) -> str:
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        run = uow.runs.create(Run(owner_id="u1", task_id="t1", team_id="tm1"))
    return run.id


def test_persist_run_state_updates_row():
    factory = _factory()
    run_id = _seed_run(factory)
    acts = RunActivities(factory, FakeAgentRuntime())
    acts.persist_run_state({"run_id": run_id, "owner_id": "u1",
                            "status": RunStatus.RUNNING, "stage": RunStage.PLAN, "cost_usd": 1.0})
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        run = uow.runs.get(run_id)
    assert run.status == "running" and run.stage == "plan" and run.cost_usd == 1.0


def test_run_stage_records_events_and_returns_result():
    factory = _factory()
    run_id = _seed_run(factory)
    acts = RunActivities(factory, FakeAgentRuntime())
    result = acts.run_stage({"run_id": run_id, "owner_id": "u1", "stage": RunStage.PLAN,
                             "task_title": "T", "acceptance_criteria": [], "workspace_path": "/tmp/x"})
    assert result["outcome"] == "ok"
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        page = uow.run_events.list(filters={"run_id": run_id})
    assert page.total >= 1
```

- [ ] **Step 2: Run red** → ImportError.

- [ ] **Step 3: Implement** `src/adapters/temporal/activities.py`. Activities are **sync** methods (the worker runs them in a thread pool). They are decorated with `@activity.defn` and use Temporal's heartbeat when running inside a worker (guarded so they also run in plain unit tests):
```python
from temporalio import activity

from adapters.database.uow import SqlUnitOfWork
from domain.models import (
    Run, RunEvent, RunEventType, RunStage, RunStatus, utc_now,
)
from domain.runtime import AgentRuntime, RunContext
from adapters.runtime.fake import result_of


def _heartbeat(detail: str) -> None:
    try:
        activity.heartbeat(detail)
    except RuntimeError:
        pass  # not running inside a Temporal activity (unit test)


class RunActivities:
    """Holds the session factory + runtime; exposes Temporal activities.
    The ONLY DB writer during a run."""

    def __init__(self, session_factory, runtime: AgentRuntime):
        self._session_factory = session_factory
        self._runtime = runtime

    def _uow(self, owner_id: str) -> SqlUnitOfWork:
        return SqlUnitOfWork(self._session_factory, required_filters={"owner_id": owner_id})

    @activity.defn(name="persist_run_state")
    def persist_run_state(self, payload: dict) -> None:
        uow = self._uow(payload["owner_id"])
        with uow.transaction():
            run = uow.runs.get(payload["run_id"])
            updates = {}
            if payload.get("status") is not None:
                updates["status"] = RunStatus(payload["status"])
            if payload.get("stage") is not None:
                updates["stage"] = RunStage(payload["stage"])
            if payload.get("cost_usd") is not None:
                updates["cost_usd"] = float(payload["cost_usd"])
            if updates:
                uow.runs.update(payload["run_id"], run.model_copy(update=updates))

    @activity.defn(name="record_event")
    def record_event(self, payload: dict) -> None:
        uow = self._uow(payload["owner_id"])
        with uow.transaction():
            uow.run_events.create(RunEvent(
                run_id=payload["run_id"],
                owner_id=payload["owner_id"],
                stage=RunStage(payload["stage"]) if payload.get("stage") else None,
                type=RunEventType(payload["type"]),
                message=payload.get("message", ""),
                created_at=utc_now(),
            ))

    @activity.defn(name="run_stage")
    def run_stage(self, payload: dict) -> dict:
        ctx = RunContext(
            run_id=payload["run_id"],
            stage=RunStage(payload["stage"]),
            task_title=payload["task_title"],
            acceptance_criteria=payload.get("acceptance_criteria", []),
            workspace_path=payload["workspace_path"],
            prior_artifacts=payload.get("prior_artifacts", {}),
        )
        events = []
        for event in self._runtime.run_stage(ctx):
            events.append(event)
            _heartbeat(event.message)
            self.record_event({
                "run_id": payload["run_id"], "owner_id": payload["owner_id"],
                "stage": payload["stage"], "type": RunEventType.AGENT_EVENT,
                "message": event.message,
            })
        return result_of(events).model_dump()
```

- [ ] **Step 4: Run green** → PASS.

- [ ] **Step 5: Commit**
```bash
git add src/adapters/temporal/activities.py tests/unit/test_activities.py
git commit -m "feat: Temporal run activities (persist, record_event, run_stage)"
```

---

## Task T10: RunWorkflow + workflow tests

**Files:**
- Create: `src/adapters/temporal/workflow.py`
- Test: `tests/workflow/__init__.py`, `tests/workflow/test_run_workflow.py`

> Depends on T2 (pipeline), T9 (activities), T8 (client unused here but config). Needs `pytest-asyncio` (T14).

- [ ] **Step 1: Write the failing test**
```python
# tests/workflow/test_run_workflow.py
import uuid

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from concurrent.futures import ThreadPoolExecutor

from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from adapters.runtime.fake import FakeAgentRuntime
from adapters.temporal.activities import RunActivities
from adapters.temporal.workflow import RunWorkflow
from domain.models import (
    AutonomyLevel, Run, RunStage, RunStatus, AgentEvent if False else object,
)
from domain.models import Run as _Run  # noqa: F811


def _factory():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def _seed(factory, owner="u1") -> str:
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": owner})
    with uow.transaction():
        run = uow.runs.create(_Run(owner_id=owner, task_id="t1", team_id="tm1"))
    return run.id


def _run_status(factory, run_id, owner="u1"):
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": owner})
    with uow.transaction():
        return uow.runs.get(run_id).status


def _input(run_id, autonomy):
    return {"run_id": run_id, "owner_id": "u1", "task_id": "t1",
            "autonomy": autonomy, "task_title": "T", "acceptance_criteria": []}


async def _worker(env, factory, runtime):
    acts = RunActivities(factory, runtime)
    return Worker(
        env.client, task_queue="test-q", workflows=[RunWorkflow],
        activities=[acts.persist_run_state, acts.record_event, acts.run_stage],
        activity_executor=ThreadPoolExecutor(max_workers=4),
    )


@pytest.mark.asyncio
async def test_full_auto_runs_to_done():
    factory = _factory()
    run_id = _seed(factory)
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with await _worker(env, factory, FakeAgentRuntime()):
            await env.client.execute_workflow(
                RunWorkflow.run, _input(run_id, AutonomyLevel.FULL_AUTO),
                id=run_id, task_queue="test-q",
            )
    assert _run_status(factory, run_id) == RunStatus.DONE


@pytest.mark.asyncio
async def test_gated_all_waits_then_approves_to_done():
    factory = _factory()
    run_id = _seed(factory)
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with await _worker(env, factory, FakeAgentRuntime()):
            handle = await env.client.start_workflow(
                RunWorkflow.run, _input(run_id, AutonomyLevel.GATED_ALL),
                id=run_id, task_queue="test-q",
            )
            await env.client.get_workflow_handle(run_id).signal("approve")  # plan gate
            await env.client.get_workflow_handle(run_id).signal("approve")  # merge gate
            await handle.result()
    assert _run_status(factory, run_id) == RunStatus.DONE


@pytest.mark.asyncio
async def test_reject_ends_failed():
    factory = _factory()
    run_id = _seed(factory)
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with await _worker(env, factory, FakeAgentRuntime()):
            handle = await env.client.start_workflow(
                RunWorkflow.run, _input(run_id, AutonomyLevel.GATED_ALL),
                id=run_id, task_queue="test-q",
            )
            await env.client.get_workflow_handle(run_id).signal("reject")
            await handle.result()
    assert _run_status(factory, run_id) == RunStatus.FAILED


@pytest.mark.asyncio
async def test_verify_exhausted_blocks():
    factory = _factory()
    run_id = _seed(factory)
    from domain.runtime import AgentEvent as AE, StageResult
    script = {RunStage.VERIFY: [AE(type="result", stage=RunStage.VERIFY,
              data=StageResult(outcome="fail").model_dump())]}
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with await _worker(env, factory, FakeAgentRuntime(script=script)):
            await env.client.execute_workflow(
                RunWorkflow.run, _input(run_id, AutonomyLevel.FULL_AUTO),
                id=run_id, task_queue="test-q",
            )
    assert _run_status(factory, run_id) == RunStatus.BLOCKED
```
> Clean up the import line: the `AgentEvent if False else object` line above is illustrative — the actual top imports you need are: `AutonomyLevel, Run, RunStage, RunStatus` from `domain.models`. Remove the noqa juggling and import `Run` directly. (Keep tests tidy.)

- [ ] **Step 2: Run red** → import error / workflow missing.

- [ ] **Step 3: Implement** `src/adapters/temporal/workflow.py`. The workflow is deterministic; it imports the pure pipeline policy through the sandbox passthrough and calls activities by registered name:
```python
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from domain import pipeline
    from domain.models import AutonomyLevel, RunEventType, RunStage, RunStatus

_STAGE_TIMEOUT = timedelta(minutes=10)
_RETRY = RetryPolicy(maximum_attempts=3)


@workflow.defn(name="RunWorkflow")
class RunWorkflow:
    def __init__(self) -> None:
        self._approved = False
        self._rejected = False
        self._cancelled = False

    @workflow.signal
    def approve(self) -> None:
        self._approved = True

    @workflow.signal
    def reject(self) -> None:
        self._rejected = True

    @workflow.signal
    def cancel(self) -> None:
        self._cancelled = True

    async def _persist(self, run_id, owner_id, **fields) -> None:
        await workflow.execute_activity(
            "persist_run_state", {"run_id": run_id, "owner_id": owner_id, **fields},
            start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY,
        )

    async def _event(self, run_id, owner_id, stage, type_, message="") -> None:
        await workflow.execute_activity(
            "record_event",
            {"run_id": run_id, "owner_id": owner_id, "stage": stage, "type": type_, "message": message},
            start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY,
        )

    @workflow.run
    async def run(self, inp: dict) -> str:
        run_id, owner_id = inp["run_id"], inp["owner_id"]
        autonomy = AutonomyLevel(inp["autonomy"])
        gates = pipeline.gates_for(autonomy)
        cost = 0.0
        verify_loops = 0

        i = 0
        while i < len(pipeline.STAGES):
            if self._cancelled:
                await self._persist(run_id, owner_id, status=RunStatus.CANCELLED)
                return RunStatus.CANCELLED

            stage = pipeline.STAGES[i]
            await self._persist(run_id, owner_id, status=RunStatus.RUNNING, stage=stage)
            await self._event(run_id, owner_id, stage, RunEventType.STAGE_STARTED)

            result = await workflow.execute_activity(
                "run_stage",
                {"run_id": run_id, "owner_id": owner_id, "stage": stage,
                 "task_title": inp["task_title"], "acceptance_criteria": inp.get("acceptance_criteria", []),
                 "workspace_path": f"/tmp/{run_id}"},
                start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY,
            )
            cost += float(result.get("cost_usd", 0.0))
            await self._persist(run_id, owner_id, cost_usd=cost)
            await self._event(run_id, owner_id, stage, RunEventType.STAGE_COMPLETED)

            if result["outcome"] == "blocked":
                await self._persist(run_id, owner_id, status=RunStatus.BLOCKED)
                await self._event(run_id, owner_id, stage, RunEventType.BLOCKED)
                return RunStatus.BLOCKED

            if stage == RunStage.VERIFY and result["outcome"] == "fail":
                verify_loops += 1
                if pipeline.should_retry_verify(verify_loops):
                    i = pipeline.STAGES.index(RunStage.IMPLEMENT)  # loop back
                    continue
                await self._persist(run_id, owner_id, status=RunStatus.BLOCKED)
                await self._event(run_id, owner_id, stage, RunEventType.BLOCKED, "verify exhausted")
                return RunStatus.BLOCKED

            if stage in gates:
                await self._persist(run_id, owner_id, status=RunStatus.AWAITING_APPROVAL)
                await self._event(run_id, owner_id, stage, RunEventType.GATE_OPENED)
                await workflow.wait_condition(
                    lambda: self._approved or self._rejected or self._cancelled
                )
                if self._cancelled:
                    await self._persist(run_id, owner_id, status=RunStatus.CANCELLED)
                    return RunStatus.CANCELLED
                if self._rejected:
                    await self._persist(run_id, owner_id, status=RunStatus.FAILED)
                    await self._event(run_id, owner_id, stage, RunEventType.GATE_RESOLVED, "rejected")
                    return RunStatus.FAILED
                self._approved = False  # reset for the next gate
                await self._event(run_id, owner_id, stage, RunEventType.GATE_RESOLVED, "approved")

            i += 1

        await self._persist(run_id, owner_id, status=RunStatus.DONE, stage=RunStage.LEARN)
        return RunStatus.DONE
```

- [ ] **Step 4: Run green** → `uv run pytest tests/workflow/ -v` PASS (all 4).

- [ ] **Step 5: Commit**
```bash
git add src/adapters/temporal/workflow.py tests/workflow
git commit -m "feat: RunWorkflow (staged pipeline, gates, verify retry, cancel)"
```

---

## Task T11: Worker entrypoint

**Files:**
- Create: `src/adapters/temporal/worker.py`, `src/interactors/worker_main.py`
- Test: `tests/unit/test_worker_build.py`

> Depends on T9, T10, T5.

- [ ] **Step 1: Write the failing test** (build the worker object without connecting):
```python
# tests/unit/test_worker_build.py
from adapters.temporal.worker import build_activities


def test_build_activities_returns_three_callables():
    acts = build_activities("sqlite:///:memory:")
    assert len(acts) == 3
    assert all(callable(a) for a in acts)
```

- [ ] **Step 2: Run red** → ImportError.

- [ ] **Step 3: Implement** `src/adapters/temporal/worker.py`:
```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.runtime.fake import FakeAgentRuntime
from adapters.temporal.activities import RunActivities
from adapters.temporal.config import TemporalConfig
from adapters.temporal.workflow import RunWorkflow


def build_activities(database_url: str) -> list:
    engine = make_engine(database_url)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    acts = RunActivities(factory, FakeAgentRuntime())
    return [acts.persist_run_state, acts.record_event, acts.run_stage]


async def run_worker(config: TemporalConfig, database_url: str) -> None:
    client = await Client.connect(config.address, namespace=config.namespace)
    worker = Worker(
        client,
        task_queue=config.task_queue,
        workflows=[RunWorkflow],
        activities=build_activities(database_url),
        activity_executor=ThreadPoolExecutor(max_workers=8),
    )
    await worker.run()


def main(config: TemporalConfig, database_url: str) -> None:
    asyncio.run(run_worker(config, database_url))
```

`src/interactors/worker_main.py`:
```python
from adapters.temporal.config import TemporalConfig
from adapters.temporal.worker import main
from interactors.api.settings import Settings


def run() -> None:
    settings = Settings()
    main(TemporalConfig.from_settings(settings), settings.database_url)


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run green** → PASS.

- [ ] **Step 5: Commit**
```bash
git add src/adapters/temporal/worker.py src/interactors/worker_main.py tests/unit/test_worker_build.py
git commit -m "feat: Temporal worker entrypoint"
```

---

## Task T12: API temporal_client dependency

**Files:**
- Modify: `src/interactors/api/deps.py`
- Test: covered via T13 (no standalone test needed; dependency is wiring).

- [ ] **Step 1: Implement** — add to `src/interactors/api/deps.py`:
```python
from adapters.temporal.client import TemporalRunClient
from adapters.temporal.config import TemporalConfig


def temporal_client(request: Request) -> TemporalRunClient:
    return TemporalRunClient(TemporalConfig.from_settings(request.app.state.settings))
```

- [ ] **Step 2: Verify it imports**

Run: `uv run python -c "import interactors.api.deps"`
Expected: no error.

- [ ] **Step 3: Commit**
```bash
git add src/interactors/api/deps.py
git commit -m "feat: temporal_client API dependency"
```

---

## Task T13: Refactor runs router (start workflow + signal gates + events)

**Files:**
- Modify: `src/interactors/api/routes/runs.py`
- Test: `tests/integration/test_runs_api.py`

> Depends on T7 (run_events), T8 (client), T12 (dep). This rewrites the A2 gate endpoints.

- [ ] **Step 1: Write the failing tests** — use a fake Temporal client via dependency override. Add to `tests/integration/test_runs_api.py`:
```python
from interactors.api.deps import temporal_client


class _FakeTemporal:
    def __init__(self):
        self.started = []
        self.signals = []

    def start_run_workflow(self, run_input): self.started.append(run_input)
    def signal(self, run_id, name): self.signals.append((run_id, name))


def _client_with_fake_temporal():
    from interactors.api.app import create_app
    from interactors.api.settings import Settings
    from fastapi.testclient import TestClient
    app = create_app(Settings(_env_file=None, database_url="sqlite:///:memory:"))
    fake = _FakeTemporal()
    app.dependency_overrides[temporal_client] = lambda: fake
    return TestClient(app), fake


def test_start_run_starts_workflow():
    c, fake = _client_with_fake_temporal()
    task_id, _team, _pid = _ready_task(c)
    resp = c.post(f"/work-items/{task_id}/runs")
    assert resp.status_code == 201
    assert len(fake.started) == 1
    assert fake.started[0]["run_id"] == resp.json()["data"]["id"]


def test_approve_sends_signal_only_when_awaiting():
    c, fake = _client_with_fake_temporal()
    run_id = _seed_awaiting_run(c)  # helper from A3-aware test (status awaiting_approval)
    resp = c.post(f"/runs/{run_id}/approve")
    assert resp.status_code == 202
    assert (run_id, "approve") in fake.signals


def test_approve_pending_run_is_409():
    c, fake = _client_with_fake_temporal()
    task_id, _t, _p = _ready_task(c)
    run_id = c.post(f"/work-items/{task_id}/runs").json()["data"]["id"]  # pending
    resp = c.post(f"/runs/{run_id}/approve")
    assert resp.status_code == 409
    assert fake.signals == []


def test_list_run_events():
    c, fake = _client_with_fake_temporal()
    run_id = _seed_awaiting_run(c)
    resp = c.get(f"/runs/{run_id}/events")
    assert resp.status_code == 200
    assert "data" in resp.json()
```
> Update the existing `_seed_awaiting_run` helper to seed status `awaiting_approval` (it already does for the A2 gate tests). The old A2 tests asserting approve→`done` directly must be **updated** to the new signal behavior (202 + signal recorded), since the workflow — not the endpoint — now sets status.

- [ ] **Step 2: Run red** → existing approve/reject tests fail (old behavior) + new tests fail.

- [ ] **Step 3: Implement** — rewrite `src/interactors/api/routes/runs.py`:
```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from adapters.database.ports import UnitOfWork
from adapters.temporal.client import TemporalRunClient
from domain.models import Run, RunStatus, WorkItemKind, WorkItemStatus, utc_now
from domain.transitions import validate_transition
from interactors.api.deps import get_uow, temporal_client
from interactors.api.envelope import ok

router = APIRouter(tags=["runs"])


@router.post("/work-items/{task_id}/runs", status_code=201)
def start_run(
    task_id: str,
    uow: UnitOfWork = Depends(get_uow),
    temporal: TemporalRunClient = Depends(temporal_client),
) -> dict:
    with uow.transaction():
        task = uow.work_items.get(task_id)
        if task.kind != WorkItemKind.TASK:
            raise HTTPException(status_code=404, detail="task not found")
        if task.status != WorkItemStatus.READY:
            raise HTTPException(status_code=409, detail=f"task is {task.status}, must be ready")
        validate_transition(task.status, WorkItemStatus.IN_PROGRESS)
        project = uow.projects.get(task.project_id)
        if not project.team_id:
            raise HTTPException(status_code=409, detail="project has no team assigned")
        run = uow.runs.create(Run(owner_id=project.owner_id, task_id=task_id, team_id=project.team_id))
        uow.work_items.update(
            task_id,
            task.model_copy(update={"status": WorkItemStatus.IN_PROGRESS, "updated_at": utc_now()}),
        )
        run_input = {
            "run_id": run.id, "owner_id": run.owner_id, "task_id": task_id,
            "autonomy": project.autonomy, "task_title": task.title,
            "acceptance_criteria": task.acceptance_criteria,
        }
    temporal.start_run_workflow(run_input)  # after commit: the run row exists for the worker
    return ok(run.model_dump(mode="json"))


@router.get("/work-items/{task_id}/runs")
def list_runs(task_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        uow.work_items.get(task_id)
        page = uow.runs.list(filters={"task_id": task_id}, order_by="-created_at")
    return ok([r.model_dump(mode="json") for r in page.results],
              meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number})


@router.get("/runs/{run_id}")
def get_run(run_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        run = uow.runs.get(run_id)
    return ok(run.model_dump(mode="json"))


@router.get("/runs/{run_id}/events")
def list_run_events(run_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        uow.runs.get(run_id)  # 404 if unknown / cross-tenant
        page = uow.run_events.list(filters={"run_id": run_id}, order_by="created_at", page_size=200)
    return ok([e.model_dump(mode="json") for e in page.results],
              meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number})


def _signal(run_id: str, name: str, *, require_gate: bool, uow: UnitOfWork,
            temporal: TemporalRunClient) -> dict:
    with uow.transaction():
        run = uow.runs.get(run_id)
        if require_gate and run.status != RunStatus.AWAITING_APPROVAL:
            raise HTTPException(status_code=409, detail=f"run is {run.status}, not awaiting approval")
        if not require_gate and run.status in (RunStatus.DONE, RunStatus.FAILED, RunStatus.CANCELLED):
            raise HTTPException(status_code=409, detail=f"run is terminal ({run.status})")
    temporal.signal(run_id, name)
    return run.model_dump(mode="json")


@router.post("/runs/{run_id}/approve", status_code=202)
def approve_run(run_id: str, uow: UnitOfWork = Depends(get_uow),
                temporal: TemporalRunClient = Depends(temporal_client)) -> dict:
    return ok(_signal(run_id, "approve", require_gate=True, uow=uow, temporal=temporal))


@router.post("/runs/{run_id}/reject", status_code=202)
def reject_run(run_id: str, uow: UnitOfWork = Depends(get_uow),
               temporal: TemporalRunClient = Depends(temporal_client)) -> dict:
    return ok(_signal(run_id, "reject", require_gate=True, uow=uow, temporal=temporal))


@router.post("/runs/{run_id}/cancel", status_code=202)
def cancel_run(run_id: str, uow: UnitOfWork = Depends(get_uow),
               temporal: TemporalRunClient = Depends(temporal_client)) -> dict:
    return ok(_signal(run_id, "cancel", require_gate=False, uow=uow, temporal=temporal))


class UpdateRun(BaseModel):
    stage: str | None = None
    branch: str | None = None
    pr_url: str | None = None


@router.patch("/runs/{run_id}")
def patch_run(run_id: str, body: UpdateRun, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        run = uow.runs.get(run_id)
        result = uow.runs.update(run_id, run.model_copy(update=body.model_dump(exclude_none=True)))
    return ok(result.model_dump(mode="json"))
```

- [ ] **Step 4: Run green**

Run: `uv run pytest tests/integration/test_runs_api.py -v`
Expected: PASS (new + updated tests). Fix any old A2 assertions that expected approve→`done` directly.

- [ ] **Step 5: Commit**
```bash
git add src/interactors/api/routes/runs.py tests/integration/test_runs_api.py
git commit -m "refactor: runs endpoints start workflow + signal gates; add events route"
```

---

## Task T14: Add temporalio + pytest-asyncio deps

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dependencies**

Add `"temporalio>=1.7"` to `[project].dependencies`, and `"pytest-asyncio>=0.24"` to `[dependency-groups].dev`. Add under `[tool.pytest.ini_options]`: `asyncio_mode = "auto"`.

- [ ] **Step 2: Sync + verify**

Run: `uv sync && uv run python -c "import temporalio; import pytest_asyncio; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Commit**
```bash
git add pyproject.toml uv.lock
git commit -m "chore: add temporalio + pytest-asyncio"
```

---

## Task T15: docker-compose Temporal + Makefile + docs

**Files:**
- Modify: `docker-compose.yml`, `Makefile`, `CLAUDE.md`

- [ ] **Step 1: Add the Temporal dev-server service** to `docker-compose.yml` under `services:`:
```yaml
  temporal:
    image: temporalio/admin-tools:1.25
    command: ["temporal", "server", "start-dev", "--ip", "0.0.0.0", "--db-filename", "/data/temporal.db"]
    ports:
      - "7233:7233"
      - "8233:8233"   # Web UI
    volumes:
      - temporaldata:/data
    healthcheck:
      test: ["CMD", "temporal", "operator", "cluster", "health", "--address", "127.0.0.1:7233"]
      interval: 5s
      timeout: 3s
      retries: 20
```
And add `temporaldata:` under the top-level `volumes:`.

- [ ] **Step 2: Add Makefile targets** (append):
```makefile
temporal:
	docker compose up -d temporal

worker:
	uv run python -m interactors.worker_main
```

- [ ] **Step 3: Update `CLAUDE.md` dev commands** — add under the Dev commands block:
```bash
docker compose up -d temporal     # Temporal dev server (UI on :8233)
make worker                       # run the Temporal worker (pipeline executor)
```

- [ ] **Step 4: Verify compose config parses**

Run: `docker compose config >/dev/null && echo OK`
Expected: `OK`.

- [ ] **Step 5: Commit**
```bash
git add docker-compose.yml Makefile CLAUDE.md
git commit -m "chore: Temporal dev-server compose service + worker make target + docs"
```

---

## Task T16: Full suite + coverage gate

**Files:** none (verification).

- [ ] **Step 1: Run the whole backend suite with coverage**

Run: `uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80`
Expected: all pass, coverage ≥ 80%.

> If coverage dips below 80%, the usual cause is the async network code that can't run
> without a live Temporal server: `TemporalRunClient._client`/`start_run_workflow`/`signal`
> (T8) and `adapters/temporal/worker.run_worker`/`main` (T11). Mark **only those network-bound
> lines** with `# pragma: no cover` — never the workflow, activities, pipeline, or routes,
> which are all exercised by the time-skipping and faked-client tests.

- [ ] **Step 2: Lint**

Run: `uv run ruff check src tests`
Expected: All checks passed.

- [ ] **Step 3: Commit any fixes**
```bash
git add -A && git commit -m "test: green A3 suite" || echo "nothing to commit"
```

---

## Self-review notes (resolved)

- **Spec §4 layers** ↔ T2 (pipeline), T3 (runtime port), T4 (workspace port), T5/T6 (adapters), T7 (persistence), T8–T11 (temporal), T12–T13 (api). ✅
- **Spec §5 pipeline policy** ↔ T2 (`STAGES`, `gates_for`, `should_retry_verify`); `RunStage`/`RunEvent` in T1. ✅
- **Spec §6 ports + fakes** ↔ T3/T4/T5/T6. ✅
- **Spec §7 workflow/activities/signals** ↔ T9 (activities, sole DB writer), T10 (workflow, gates via `wait_condition`, verify loop, cancel), T11 (worker). ✅
- **Spec §8 API wiring** ↔ T13 (start workflow, signal gates, 202, events route) + T12 (client dep). ✅
- **Spec §9 persistence (run_events)** ↔ T7. ✅
- **Spec §10 error handling** ↔ T10 retry policy + terminal states; activities idempotent-on-status (last-writer-wins). ✅
- **Spec §11 testing** ↔ pure (T2), workflow `WorkflowEnvironment` (T10), API faked-client (T13), adapters (T5/T6/T7). ✅
- **Spec §12 dev infra** ↔ T14 (deps), T15 (compose/Makefile/docs), T8 (settings). ✅
- **Type consistency:** activity names `persist_run_state` / `record_event` / `run_stage` match between T9 (`@activity.defn(name=…)`), T10 (`execute_activity("…")`), T11 (registration). Signal names `approve`/`reject`/`cancel` match T10 (`@workflow.signal`) and T13 (`temporal.signal(id, name)`). `RunInput` dict keys (`run_id, owner_id, task_id, autonomy, task_title, acceptance_criteria`) match between T13 (built) and T10 (consumed). ✅
- **A2 behavior change:** approve/reject move from direct `done`/`failed` writes to 202 + signal; their A2 tests are updated in T13. Called out in spec §13. ✅
- **Known nuance:** `start_run` calls Temporal **after** the DB commit so the worker can read the run row; if the start call raises, surface it (the run stays `pending` and can be retried) — acceptable for A3, hardened in A4.
```
