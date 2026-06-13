# A5d Token / Usage Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture full token + cost detail from each agent stage, persist it as append-only `UsageRecord` rows (one per stage-execution per model), and expose owner-scoped rollups across the work-item hierarchy, stage, agent role, and model.

**Architecture:** A pure `TokenUsage` value object + rollup helpers in `domain/usage.py`; the `stream_json` parser captures the runtime `result` event's `usage`/`modelUsage` onto `StageResult`; a `record_usage` activity (called inside `run_stage`, the existing DB-writing activity) persists rows and recomputes `Run` token counters from those rows (idempotent on Temporal retries); three read endpoints aggregate on read via the existing repository filter DSL.

**Tech Stack:** Python 3.12, Pydantic v2, SQLAlchemy 2.0 (sync), FastAPI, Temporal (`temporalio`), pytest. Spec: `docs/specs/2026-06-13-a5d-usage-tracking-design.md`.

---

## File Structure

- `src/domain/usage.py` — **create**. `TokenUsage` value object + `rollup`/`group_by` helpers (pure).
- `src/domain/runtime.py` — **modify**. `StageResult` gains `usage` + `model_usage`.
- `src/domain/models.py` — **modify**. `UsageRecord` DTO; `Run` gains token counters.
- `src/adapters/runtime/stream_json.py` — **modify**. Parse `result.usage` + `result.modelUsage`.
- `src/adapters/runtime/fake.py` — **modify**. Default events + `result_of` carry usage.
- `src/adapters/database/orm.py` — **modify**. `UsageRecordRow`; `RunRow` token columns.
- `src/adapters/database/repositories.py` — **modify**. `UsageRecordRepository`.
- `src/adapters/database/uow.py` — **modify**. `uow.usage` property.
- `src/adapters/database/ports.py` — **modify**. `usage` on `UnitOfWork`; `UsageRecord` import.
- `src/interactors/temporal/activities.py` — **modify**. `record_usage` activity + `run_stage` hook.
- `src/interactors/temporal/worker.py` — **modify**. Register `record_usage`.
- `src/interactors/api/routes/usage.py` — **create**. Three read endpoints.
- `src/interactors/api/app.py` — **modify**. Register the usage router.
- Tests under `tests/unit/`, `tests/integration/`, `tests/workflow/`.

---

## Task 1: `TokenUsage` value object + rollup helpers

**Files:**
- Create: `src/domain/usage.py`
- Test: `tests/unit/test_usage.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_usage.py
from domain.usage import TokenUsage, ZERO_USAGE, rollup, group_by


def test_total_tokens_sums_all_four_buckets():
    u = TokenUsage(input_tokens=10, output_tokens=20, cache_read_tokens=3, cache_creation_tokens=4)
    assert u.total_tokens == 37


def test_combine_returns_new_object_and_does_not_mutate():
    a = TokenUsage(input_tokens=10, cost_usd=0.10)
    b = TokenUsage(input_tokens=5, output_tokens=2, cost_usd=0.05)
    c = a.combine(b)
    assert c.input_tokens == 15
    assert c.output_tokens == 2
    assert round(c.cost_usd, 2) == 0.15
    assert a.input_tokens == 10  # unchanged (immutability)


def test_rollup_sums_an_iterable():
    items = [TokenUsage(input_tokens=1, cost_usd=0.01), TokenUsage(input_tokens=2, cost_usd=0.02)]
    total = rollup(items)
    assert total.input_tokens == 3
    assert round(total.cost_usd, 2) == 0.03


def test_rollup_of_empty_is_zero():
    assert rollup([]) == ZERO_USAGE


def test_group_by_buckets_by_key():
    rows = [
        ("plan", TokenUsage(input_tokens=1)),
        ("plan", TokenUsage(input_tokens=2)),
        ("verify", TokenUsage(input_tokens=4)),
    ]
    grouped = group_by(rows)
    assert grouped["plan"].input_tokens == 3
    assert grouped["verify"].input_tokens == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_usage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domain.usage'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/domain/usage.py
from typing import Iterable

from pydantic import BaseModel


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_creation_tokens
        )

    def combine(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_creation_tokens=self.cache_creation_tokens + other.cache_creation_tokens,
            cost_usd=self.cost_usd + other.cost_usd,
        )


ZERO_USAGE = TokenUsage()


def rollup(items: Iterable[TokenUsage]) -> TokenUsage:
    total = ZERO_USAGE
    for item in items:
        total = total.combine(item)
    return total


def group_by(pairs: Iterable[tuple[str, TokenUsage]]) -> dict[str, TokenUsage]:
    """pairs: (bucket_key, usage). Buckets are summed via combine."""
    out: dict[str, TokenUsage] = {}
    for key, usage in pairs:
        out[key] = out.get(key, ZERO_USAGE).combine(usage)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_usage.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/domain/usage.py tests/unit/test_usage.py
git commit -m "feat: TokenUsage value object + rollup/group_by helpers"
```

---

## Task 2: `StageResult` carries usage + per-model breakdown

**Files:**
- Modify: `src/domain/runtime.py`
- Test: `tests/unit/test_runtime_dtos.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_runtime_dtos.py
from domain.runtime import StageResult
from domain.usage import TokenUsage


def test_stage_result_defaults_to_zero_usage():
    r = StageResult(outcome="ok")
    assert r.usage == TokenUsage()
    assert r.model_usage == {}


def test_stage_result_carries_per_model_usage():
    r = StageResult(
        outcome="ok",
        cost_usd=0.5,
        usage=TokenUsage(input_tokens=100, output_tokens=20, cost_usd=0.5),
        model_usage={"claude-opus-4-8": TokenUsage(input_tokens=100, output_tokens=20, cost_usd=0.5)},
    )
    assert r.usage.input_tokens == 100
    assert r.model_usage["claude-opus-4-8"].output_tokens == 20
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_runtime_dtos.py -v`
Expected: FAIL — `StageResult` has no `usage`/`model_usage` field.

- [ ] **Step 3: Write minimal implementation**

In `src/domain/runtime.py`, add the import and two fields to `StageResult`:

```python
from domain.usage import TokenUsage   # add at top, after existing imports


class StageResult(BaseModel):
    outcome: Literal["ok", "fail", "blocked"]
    artifacts: dict = {}
    cost_usd: float = 0.0
    usage: TokenUsage = TokenUsage()
    model_usage: dict[str, TokenUsage] = {}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_runtime_dtos.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/domain/runtime.py tests/unit/test_runtime_dtos.py
git commit -m "feat: StageResult carries TokenUsage + per-model breakdown"
```

---

## Task 3: Parse `usage` + `modelUsage` from the runtime result event

**Files:**
- Modify: `src/adapters/runtime/stream_json.py`
- Test: `tests/unit/test_stream_json_usage.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_stream_json_usage.py
import json

from adapters.runtime import stream_json
from domain.models import RunStage


def _result_line(**result_obj):
    return json.dumps({"type": "result", **result_obj})


def test_parse_captures_top_level_usage():
    line = _result_line(
        is_error=False,
        result="done",
        total_cost_usd=0.42,
        usage={
            "input_tokens": 100,
            "output_tokens": 30,
            "cache_read_input_tokens": 5,
            "cache_creation_input_tokens": 7,
        },
    )
    _events, result = stream_json.parse([line], RunStage.IMPLEMENT)
    assert result.usage.input_tokens == 100
    assert result.usage.output_tokens == 30
    assert result.usage.cache_read_tokens == 5
    assert result.usage.cache_creation_tokens == 7
    assert round(result.usage.cost_usd, 2) == 0.42


def test_parse_splits_model_usage_per_model():
    line = _result_line(
        is_error=False,
        result="done",
        total_cost_usd=0.9,
        usage={"input_tokens": 150, "output_tokens": 50},
        modelUsage={
            "claude-opus-4-8": {"inputTokens": 100, "outputTokens": 30,
                                "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0,
                                "costUSD": 0.6},
            "claude-haiku-4-5": {"inputTokens": 50, "outputTokens": 20,
                                 "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0,
                                 "costUSD": 0.3},
        },
    )
    _events, result = stream_json.parse([line], RunStage.IMPLEMENT)
    assert set(result.model_usage) == {"claude-opus-4-8", "claude-haiku-4-5"}
    assert result.model_usage["claude-opus-4-8"].input_tokens == 100
    assert round(result.model_usage["claude-haiku-4-5"].cost_usd, 2) == 0.3


def test_parse_tolerates_missing_usage():
    line = _result_line(is_error=False, result="done", total_cost_usd=0.1)
    _events, result = stream_json.parse([line], RunStage.IMPLEMENT)
    assert result.usage.total_tokens == 0
    assert result.model_usage == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_stream_json_usage.py -v`
Expected: FAIL — parser does not populate `usage`/`model_usage`.

- [ ] **Step 3: Write minimal implementation**

Replace the whole of `src/adapters/runtime/stream_json.py` with:

```python
"""Pure parser for Claude Code `--output-format stream-json` lines."""

import json
from typing import Iterable

from domain.models import RunStage
from domain.runtime import AgentEvent, StageResult
from domain.usage import TokenUsage


def _assistant_text(obj: dict) -> str:
    content = obj.get("message", {}).get("content", [])
    return " ".join(
        p.get("text", "") for p in content
        if isinstance(p, dict) and p.get("type") == "text"
    ).strip()


def _usage_from_top_level(obj: dict) -> TokenUsage:
    u = obj.get("usage") or {}
    return TokenUsage(
        input_tokens=int(u.get("input_tokens", 0)),
        output_tokens=int(u.get("output_tokens", 0)),
        cache_read_tokens=int(u.get("cache_read_input_tokens", 0)),
        cache_creation_tokens=int(u.get("cache_creation_input_tokens", 0)),
        cost_usd=float(obj.get("total_cost_usd") or 0.0),
    )


def _model_usage(obj: dict) -> dict[str, TokenUsage]:
    raw = obj.get("modelUsage") or {}
    out: dict[str, TokenUsage] = {}
    for model_id, m in raw.items():
        out[model_id] = TokenUsage(
            input_tokens=int(m.get("inputTokens", 0)),
            output_tokens=int(m.get("outputTokens", 0)),
            cache_read_tokens=int(m.get("cacheReadInputTokens", 0)),
            cache_creation_tokens=int(m.get("cacheCreationInputTokens", 0)),
            cost_usd=float(m.get("costUSD", 0.0)),
        )
    return out


def parse(lines: Iterable[str], stage: RunStage) -> tuple[list[AgentEvent], StageResult]:
    events: list[AgentEvent] = []
    result = StageResult(outcome="ok")
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = obj.get("type")
        if kind == "assistant":
            text = _assistant_text(obj)
            if text:
                events.append(AgentEvent(type="progress", stage=stage, message=text[:500]))
        elif kind == "result":
            outcome = "fail" if obj.get("is_error") else "ok"
            usage = _usage_from_top_level(obj)
            result = StageResult(
                outcome=outcome,
                cost_usd=usage.cost_usd,
                usage=usage,
                model_usage=_model_usage(obj),
                artifacts={"result": obj.get("result", "")},
            )
            events.append(AgentEvent(type="result", stage=stage, message="stage complete",
                                     data=result.model_dump()))
    return events, result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_stream_json_usage.py -v`
Expected: PASS. Also confirm no regression in existing parser tests:
`uv run pytest tests/ -k stream -v`.

- [ ] **Step 5: Commit**

```bash
git add src/adapters/runtime/stream_json.py tests/unit/test_stream_json_usage.py
git commit -m "feat: parse usage + modelUsage from runtime result event"
```

---

## Task 4: Fake runtime emits usage (so the faked pipeline records rows)

**Files:**
- Modify: `src/adapters/runtime/fake.py`
- Test: `tests/unit/test_fake_runtime_usage.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_fake_runtime_usage.py
from adapters.runtime.fake import _default_events, result_of
from domain.models import RunStage


def test_default_result_event_carries_model_usage():
    events = _default_events(RunStage.IMPLEMENT)
    result = result_of(events)
    assert result.cost_usd > 0
    assert result.model_usage, "fake stage should report at least one model's usage"
    only = next(iter(result.model_usage.values()))
    assert only.total_tokens > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_fake_runtime_usage.py -v`
Expected: FAIL — `model_usage` is empty for the default fake events.

- [ ] **Step 3: Write minimal implementation**

In `src/adapters/runtime/fake.py`, import `TokenUsage`, define a fake model id + usage, and
attach them to the default result event:

```python
from domain.usage import TokenUsage   # add to imports

_DEFAULT_COST = 0.25
_FAKE_MODEL = "fake-model"
_FAKE_USAGE = TokenUsage(input_tokens=1000, output_tokens=200,
                         cache_read_tokens=0, cache_creation_tokens=0, cost_usd=_DEFAULT_COST)


def _default_events(stage: RunStage) -> list[AgentEvent]:
    return [
        AgentEvent(type="progress", stage=stage, message=f"{stage} starting"),
        AgentEvent(type="heartbeat", stage=stage, message="working"),
        AgentEvent(
            type="result",
            stage=stage,
            message=f"{stage} complete",
            data=StageResult(
                outcome="ok",
                cost_usd=_DEFAULT_COST,
                usage=_FAKE_USAGE,
                model_usage={_FAKE_MODEL: _FAKE_USAGE},
            ).model_dump(),
        ),
    ]
```

`result_of` is unchanged (it already reconstructs `StageResult(**event.data)`, which now
includes `usage`/`model_usage`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_fake_runtime_usage.py -v`
Expected: PASS. Run the full fake-runtime suite to confirm no regression:
`uv run pytest tests/ -k fake -v`.

- [ ] **Step 5: Commit**

```bash
git add src/adapters/runtime/fake.py tests/unit/test_fake_runtime_usage.py
git commit -m "feat: fake runtime reports token usage per stage"
```

---

## Task 5: `UsageRecord` DTO + `Run` token counters

**Files:**
- Modify: `src/domain/models.py`
- Test: `tests/unit/test_usage_record_dto.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_usage_record_dto.py
from domain.models import AgentRole, Run, RunStage, UsageRecord


def test_usage_record_has_hierarchy_and_token_fields():
    r = UsageRecord(
        owner_id="dev-user",
        run_id="run1",
        work_item_id="task1",
        project_id="proj1",
        stage=RunStage.IMPLEMENT,
        agent_role=AgentRole.BACKEND,
        model_id="claude-opus-4-8",
        input_tokens=100,
        output_tokens=20,
        cost_usd=0.5,
    )
    assert r.id and len(r.id) == 32
    assert r.agent_role == AgentRole.BACKEND
    assert r.dedupe_key == "run1:implement:backend:claude-opus-4-8"


def test_usage_record_agent_role_optional():
    r = UsageRecord(owner_id="u", run_id="r", work_item_id="w", project_id="p",
                    stage=RunStage.PLAN, model_id="m")
    assert r.agent_role is None
    assert r.dedupe_key == "r:plan:none:m"


def test_run_defaults_token_counters_to_zero():
    run = Run(owner_id="u", task_id="t", team_id="tm")
    assert run.input_tokens == 0
    assert run.output_tokens == 0
    assert run.cache_read_tokens == 0
    assert run.cache_creation_tokens == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_usage_record_dto.py -v`
Expected: FAIL — `UsageRecord` does not exist; `Run` has no token counters.

- [ ] **Step 3: Write minimal implementation**

In `src/domain/models.py`, add token counters to `Run` and append `UsageRecord` after it:

```python
class Run(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    task_id: str
    team_id: str
    status: RunStatus = RunStatus.PENDING
    stage: str | None = None
    branch: str | None = None
    pr_url: str | None = None
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    created_at: datetime = Field(default_factory=utc_now)


class UsageRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    run_id: str
    work_item_id: str
    project_id: str
    stage: RunStage
    agent_role: AgentRole | None = None
    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float = 0.0
    created_at: datetime = Field(default_factory=utc_now)

    @property
    def dedupe_key(self) -> str:
        role = self.agent_role.value if self.agent_role else "none"
        return f"{self.run_id}:{self.stage.value}:{role}:{self.model_id}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_usage_record_dto.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/domain/models.py tests/unit/test_usage_record_dto.py
git commit -m "feat: UsageRecord DTO + Run token counters"
```

---

## Task 6: `UsageRecordRow` ORM + `RunRow` token columns + unique dedupe index

**Files:**
- Modify: `src/adapters/database/orm.py`
- Test: `tests/unit/test_usage_orm.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_usage_orm.py
from sqlalchemy import create_engine, inspect

from adapters.database.orm import Base


def test_usage_records_table_and_run_token_columns_exist():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    insp = inspect(engine)
    assert "usage_records" in insp.get_table_names()
    usage_cols = {c["name"] for c in insp.get_columns("usage_records")}
    assert {"run_id", "work_item_id", "project_id", "stage", "agent_role",
            "model_id", "input_tokens", "cost_usd", "dedupe_key"} <= usage_cols
    run_cols = {c["name"] for c in insp.get_columns("runs")}
    assert {"input_tokens", "output_tokens", "cache_read_tokens",
            "cache_creation_tokens"} <= run_cols
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_usage_orm.py -v`
Expected: FAIL — `usage_records` table absent; `runs` lacks token columns.

- [ ] **Step 3: Write minimal implementation**

In `src/adapters/database/orm.py`: extend the SQLAlchemy import line, add the four token
columns to `RunRow` (after `cost_usd`), and add `UsageRecordRow` at the end.

```python
from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, UniqueConstraint
```

```python
# inside RunRow, after the cost_usd column:
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_creation_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```

```python
class UsageRecordRow(Base):
    __tablename__ = "usage_records"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_usage_dedupe"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    work_item_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(30), nullable=False)
    agent_role: Mapped[str | None] = mapped_column(String(20))
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_creation_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    dedupe_key: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

> `dedupe_key` is a stored column but a *derived* property on the DTO (not a DTO field), so
> the repository maps it manually — see Task 7.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_usage_orm.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/adapters/database/orm.py tests/unit/test_usage_orm.py
git commit -m "feat: usage_records table + run token columns"
```

---

## Task 7: `UsageRecordRepository` + `uow.usage` + ports

**Files:**
- Modify: `src/adapters/database/repositories.py`
- Modify: `src/adapters/database/uow.py`
- Modify: `src/adapters/database/ports.py`
- Test: `tests/unit/test_usage_repository.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_usage_repository.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.errors import IntegrityConflict
from domain.models import RunStage, UsageRecord


@pytest.fixture
def uow():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    return SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})


def _rec(**kw):
    base = dict(owner_id="dev-user", run_id="r1", work_item_id="t1", project_id="p1",
                stage=RunStage.IMPLEMENT, model_id="m1", input_tokens=10, cost_usd=0.1)
    base.update(kw)
    return UsageRecord(**base)


def test_create_and_list_usage_record(uow):
    with uow.transaction():
        uow.usage.create(_rec())
        page = uow.usage.list(filters={"run_id": "r1"})
    assert page.total == 1
    assert page.results[0].input_tokens == 10


def test_duplicate_dedupe_key_raises_integrity_conflict(uow):
    with uow.transaction():
        uow.usage.create(_rec())
    with pytest.raises(IntegrityConflict):
        with uow.transaction():
            uow.usage.create(_rec())  # same run/stage/role/model -> same dedupe_key


def test_owner_scoping_hides_other_tenants(uow):
    with uow.transaction():
        uow.usage.create(_rec(owner_id="dev-user"))
    other = SqlUnitOfWork(uow._session_factory, required_filters={"owner_id": "someone-else"})
    with other.transaction():
        page = other.usage.list(filters={"run_id": "r1"})
    assert page.total == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_usage_repository.py -v`
Expected: FAIL — `uow.usage` does not exist.

- [ ] **Step 3: Write minimal implementation**

`src/adapters/database/repositories.py` — add to the `adapters.database.orm` import and the
`domain.models` import, then add the subclass:

```python
from adapters.database.orm import (
    # ...existing names...
    UsageRecordRow,
)
from domain.models import (
    # ...existing names...
    UsageRecord,
)
from sqlalchemy.exc import IntegrityError as _SQLIntegrityError

from domain.errors import IntegrityConflict


class UsageRecordRepository(SqlRepository[UsageRecord]):
    orm_model = UsageRecordRow
    dto = UsageRecord

    def create(self, obj: UsageRecord) -> UsageRecord:
        data = obj.model_dump()
        data["dedupe_key"] = obj.dedupe_key  # stored column, derived on the DTO
        row = self.orm_model(**data)
        try:
            self._session.add(row)
            self._session.flush()
        except _SQLIntegrityError as err:
            raise IntegrityConflict(str(err.orig)) from err
        return self._to_dto(row)

    def _to_dto(self, row) -> UsageRecord:
        data = {k: v for k, v in row.__dict__.items()
                if not k.startswith("_") and k != "dedupe_key"}
        return UsageRecord(**data)
```

`src/adapters/database/uow.py` — add `UsageRecordRepository` to the existing
`from adapters.database.repositories import (...)` block, then add the property:

```python
    @property
    def usage(self) -> UsageRecordRepository:
        return UsageRecordRepository(self.session, self._required_filters)
```

`src/adapters/database/ports.py` — add `UsageRecord` to the `domain.models` import and a
property on the `UnitOfWork` Protocol:

```python
    @property
    def usage(self) -> Repository[UsageRecord]: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_usage_repository.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/adapters/database/repositories.py src/adapters/database/uow.py src/adapters/database/ports.py tests/unit/test_usage_repository.py
git commit -m "feat: UsageRecordRepository + uow.usage + ports"
```

---

## Task 8: `record_usage` activity + `run_stage` hook + worker registration

The workflow already accumulates `cost_usd` (`workflows.py:119-120`) and sets it absolutely on
the run; **leave that untouched** to avoid double-counting cost. `record_usage` writes the
append-only rows and recomputes `Run` **token** counters from those rows (so Temporal retries
of `run_stage` are idempotent: rows dedupe by `dedupe_key`, counters are recomputed, not
incremented).

**Files:**
- Modify: `src/interactors/temporal/activities.py`
- Modify: `src/interactors/temporal/worker.py`
- Test: `tests/workflow/test_record_usage.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/workflow/test_record_usage.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.models import (
    AgentRole, Project, Run, WorkItem, WorkItemKind, WorkItemStatus,
)
from interactors.temporal.activities import RunActivities


@pytest.fixture
def factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _seed(factory):
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        uow.projects.create(Project(id="p1", owner_id="dev-user", name="P", local_path="/tmp/x"))
        uow.work_items.create(WorkItem(id="t1", owner_id="dev-user", project_id="p1",
                                       kind=WorkItemKind.TASK, parent_id="f1", title="T",
                                       status=WorkItemStatus.IN_PROGRESS))
        uow.runs.create(Run(id="r1", owner_id="dev-user", task_id="t1", team_id="tm"))


def test_record_usage_writes_rows_and_recomputes_run_counters(factory):
    _seed(factory)
    acts = RunActivities(factory, runtime=None, storage=None, git=None, forge=None)
    payload = {
        "run_id": "r1", "owner_id": "dev-user", "stage": "implement",
        "agent_role": AgentRole.BACKEND.value,
        "model_usage": {"m1": {"input_tokens": 100, "output_tokens": 20,
                               "cache_read_tokens": 0, "cache_creation_tokens": 0,
                               "cost_usd": 0.5}},
    }
    acts.record_usage(payload)

    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        rows = uow.usage.list(filters={"run_id": "r1"}).results
        run = uow.runs.get("r1")
    assert len(rows) == 1
    assert rows[0].work_item_id == "t1" and rows[0].project_id == "p1"
    assert rows[0].agent_role == AgentRole.BACKEND
    assert run.input_tokens == 100 and run.output_tokens == 20


def test_record_usage_is_idempotent_on_retry(factory):
    _seed(factory)
    acts = RunActivities(factory, runtime=None, storage=None, git=None, forge=None)
    payload = {
        "run_id": "r1", "owner_id": "dev-user", "stage": "implement", "agent_role": None,
        "model_usage": {"m1": {"input_tokens": 100, "output_tokens": 20,
                               "cache_read_tokens": 0, "cache_creation_tokens": 0,
                               "cost_usd": 0.5}},
    }
    acts.record_usage(payload)
    acts.record_usage(payload)  # retry: same dedupe_key

    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        rows = uow.usage.list(filters={"run_id": "r1"}).results
        run = uow.runs.get("r1")
    assert len(rows) == 1               # not duplicated
    assert run.input_tokens == 100      # counter recomputed, not doubled
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/workflow/test_record_usage.py -v`
Expected: FAIL — `RunActivities` has no `record_usage`.

- [ ] **Step 3: Write minimal implementation**

In `src/interactors/temporal/activities.py`, extend the imports:

```python
from domain.errors import IntegrityConflict
from domain.models import (
    AgentRole, RunEvent, RunEventType, RunStage, RunStatus, UsageRecord, utc_now,
)
from domain.usage import TokenUsage
```

Add the activity (after `record_event`):

```python
    @activity.defn(name="record_usage")
    def record_usage(self, payload: dict) -> None:
        """Write one UsageRecord per model for a stage execution and recompute the run's
        token counters from all its rows. Idempotent: duplicate (run, stage, role, model)
        inserts are swallowed; counters are recomputed, never incremented."""
        owner_id = payload["owner_id"]
        run_id = payload["run_id"]
        stage = RunStage(payload["stage"])
        role = AgentRole(payload["agent_role"]) if payload.get("agent_role") else None
        uow = self._uow(owner_id)
        with uow.transaction():
            run = uow.runs.get(run_id)
            task = uow.work_items.get(run.task_id)
            for model_id, u in (payload.get("model_usage") or {}).items():
                usage = TokenUsage(**u)
                record = UsageRecord(
                    owner_id=owner_id, run_id=run_id, work_item_id=run.task_id,
                    project_id=task.project_id, stage=stage, agent_role=role,
                    model_id=model_id,
                    input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                    cache_read_tokens=usage.cache_read_tokens,
                    cache_creation_tokens=usage.cache_creation_tokens,
                    cost_usd=usage.cost_usd,
                )
                try:
                    uow.usage.create(record)
                except IntegrityConflict:
                    pass  # already recorded on a prior attempt
            rows = uow.usage.list(filters={"run_id": run_id}, page_size=1000).results
            totals = TokenUsage()
            for r in rows:
                totals = totals.combine(TokenUsage(
                    input_tokens=r.input_tokens, output_tokens=r.output_tokens,
                    cache_read_tokens=r.cache_read_tokens,
                    cache_creation_tokens=r.cache_creation_tokens))
            uow.runs.update(run_id, run.model_copy(update={
                "input_tokens": totals.input_tokens,
                "output_tokens": totals.output_tokens,
                "cache_read_tokens": totals.cache_read_tokens,
                "cache_creation_tokens": totals.cache_creation_tokens,
            }))
```

Wire it into `run_stage`. Initialise `agent_role = None` just before the `if team_id:` block;
inside the existing `if selected is not None:` branch (where `agent_manifest` is set) also set
`agent_role = selected.role`. Then replace the event loop tail of `run_stage` with:

```python
        events = []
        for event in self._runtime.run_stage(ctx):
            events.append(event)
            _heartbeat(event.message)
            self.record_event({
                "run_id": payload["run_id"], "owner_id": payload["owner_id"],
                "stage": payload["stage"], "type": RunEventType.AGENT_EVENT,
                "message": event.message,
            })
        result = result_of(events)
        if result.model_usage:
            self.record_usage({
                "run_id": payload["run_id"], "owner_id": payload["owner_id"],
                "stage": payload["stage"],
                "agent_role": agent_role.value if agent_role else None,
                "model_usage": {m: u.model_dump() for m, u in result.model_usage.items()},
            })
        return result.model_dump()
```

In `src/interactors/temporal/worker.py`, register `record_usage` in `build_activities`:

```python
    return [acts.persist_run_state, acts.record_event, acts.record_usage, acts.run_stage,
            acts.cleanup_workspace, acts.provision_workspace, acts.open_pr]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/workflow/test_record_usage.py -v`
Expected: PASS (2 tests). Then the existing workflow suite to confirm the `run_stage` change
didn't break the pipeline: `uv run pytest tests/workflow/ -v`.

- [ ] **Step 5: Commit**

```bash
git add src/interactors/temporal/activities.py src/interactors/temporal/worker.py tests/workflow/test_record_usage.py
git commit -m "feat: record_usage activity writes rows + recomputes run token counters"
```

---

## Task 9: Read API — `GET /runs/{id}/usage`

**Files:**
- Create: `src/interactors/api/routes/usage.py`
- Modify: `src/interactors/api/app.py`
- Test: `tests/integration/test_usage_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_usage_api.py
from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def _client():
    return TestClient(create_app(Settings(database_url="sqlite://", auth_mode="dev")))


def _seed_run_with_usage(client):
    app = client.app
    from adapters.database.uow import SqlUnitOfWork
    from domain.models import (Project, Run, RunStage, UsageRecord, WorkItem,
                               WorkItemKind, WorkItemStatus)
    uow = SqlUnitOfWork(app.state.session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        uow.projects.create(Project(id="p1", owner_id="dev-user", name="P", local_path="/x"))
        uow.work_items.create(WorkItem(id="e1", owner_id="dev-user", project_id="p1",
                                       kind=WorkItemKind.EPIC, title="E"))
        uow.work_items.create(WorkItem(id="f1", owner_id="dev-user", project_id="p1",
                                       kind=WorkItemKind.FEATURE, parent_id="e1", title="F"))
        uow.work_items.create(WorkItem(id="t1", owner_id="dev-user", project_id="p1",
                                       kind=WorkItemKind.TASK, parent_id="f1", title="T"))
        uow.runs.create(Run(id="r1", owner_id="dev-user", task_id="t1", team_id="tm"))
        uow.usage.create(UsageRecord(owner_id="dev-user", run_id="r1", work_item_id="t1",
                                     project_id="p1", stage=RunStage.PLAN, model_id="m1",
                                     input_tokens=10, output_tokens=2, cost_usd=0.1))
        uow.usage.create(UsageRecord(owner_id="dev-user", run_id="r1", work_item_id="t1",
                                     project_id="p1", stage=RunStage.IMPLEMENT, model_id="m1",
                                     input_tokens=90, output_tokens=8, cost_usd=0.4))


def test_run_usage_returns_totals_and_breakdown():
    client = _client()
    _seed_run_with_usage(client)
    resp = client.get("/runs/r1/usage")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["totals"]["input_tokens"] == 100
    assert round(body["data"]["totals"]["cost_usd"], 2) == 0.5
    stages = {b["stage"] for b in body["data"]["breakdown"]}
    assert stages == {"plan", "implement"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_usage_api.py::test_run_usage_returns_totals_and_breakdown -v`
Expected: FAIL — 404, route not registered.

- [ ] **Step 3: Write minimal implementation**

```python
# src/interactors/api/routes/usage.py
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from adapters.database.ports import UnitOfWork
from domain.models import UsageRecord
from domain.usage import TokenUsage, group_by, rollup
from interactors.api.deps import get_uow
from interactors.api.envelope import ok

router = APIRouter(tags=["usage"])

_GROUP_KEYS = {"stage", "agent_role", "model"}


def _usage_of(rec: UsageRecord) -> TokenUsage:
    return TokenUsage(
        input_tokens=rec.input_tokens, output_tokens=rec.output_tokens,
        cache_read_tokens=rec.cache_read_tokens,
        cache_creation_tokens=rec.cache_creation_tokens, cost_usd=rec.cost_usd,
    )


def _key_of(rec: UsageRecord, group: str) -> str:
    if group == "stage":
        return rec.stage.value
    if group == "agent_role":
        return rec.agent_role.value if rec.agent_role else "unknown"
    return rec.model_id


def _dump(u: TokenUsage) -> dict:
    return {**u.model_dump(), "total_tokens": u.total_tokens}


def _payload(records: list[UsageRecord], group: str | None) -> dict:
    data: dict = {"totals": _dump(rollup(_usage_of(r) for r in records))}
    if group:
        grouped = group_by((_key_of(r, group), _usage_of(r)) for r in records)
        data["group_by"] = group
        data["groups"] = {k: _dump(v) for k, v in grouped.items()}
    return data


def _validate_group(group: str | None) -> None:
    if group is not None and group not in _GROUP_KEYS:
        raise HTTPException(status_code=422, detail=f"group_by must be one of {_GROUP_KEYS}")


@router.get("/runs/{run_id}/usage")
def run_usage(run_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        uow.runs.get(run_id)  # 404 / owner scope
        records = uow.usage.list(filters={"run_id": run_id}, page_size=1000).results
    breakdown = [
        {"stage": r.stage.value, "model_id": r.model_id,
         "agent_role": r.agent_role.value if r.agent_role else None, **_dump(_usage_of(r))}
        for r in records
    ]
    return ok({**_payload(records, None), "breakdown": breakdown})
```

Register in `src/interactors/api/app.py`: add `usage` to the route import line and include it
after the other routers:

```python
    from interactors.api.routes import (
        agents, capabilities, projects, runs, teams, usage, work_items,
    )
    # ...existing include_router calls...
    app.include_router(usage.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_usage_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/interactors/api/routes/usage.py src/interactors/api/app.py tests/integration/test_usage_api.py
git commit -m "feat: GET /runs/{id}/usage endpoint"
```

---

## Task 10: Read API — work-item (recursive) + project rollups

**Files:**
- Modify: `src/interactors/api/routes/usage.py`
- Test: `tests/integration/test_usage_api.py` (add cases)

Work-item rollup includes the item and all descendants. Hierarchy is at most
epic → feature → task (3 levels), so resolve descendants with two `parent_id` queries.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/integration/test_usage_api.py

def test_feature_usage_rolls_up_descendant_tasks_grouped_by_stage():
    client = _client()
    _seed_run_with_usage(client)  # task t1 under feature f1 under epic e1
    resp = client.get("/work-items/f1/usage", params={"group_by": "stage"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["totals"]["input_tokens"] == 100
    assert data["groups"]["plan"]["input_tokens"] == 10
    assert data["groups"]["implement"]["input_tokens"] == 90


def test_epic_usage_includes_grandchild_task():
    client = _client()
    _seed_run_with_usage(client)
    resp = client.get("/work-items/e1/usage")
    assert resp.json()["data"]["totals"]["input_tokens"] == 100


def test_project_usage_totals_and_window_validation():
    client = _client()
    _seed_run_with_usage(client)
    assert client.get("/projects/p1/usage").json()["data"]["totals"]["input_tokens"] == 100
    bad = client.get("/projects/p1/usage", params={"since": "2030-01-01T00:00:00",
                                                   "until": "2020-01-01T00:00:00"})
    assert bad.status_code == 422


def test_invalid_group_by_is_422():
    client = _client()
    _seed_run_with_usage(client)
    assert client.get("/work-items/f1/usage", params={"group_by": "nonsense"}).status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_usage_api.py -v`
Expected: FAIL — work-item/project usage routes don't exist.

- [ ] **Step 3: Write minimal implementation**

Append to `src/interactors/api/routes/usage.py`:

```python
def _descendant_ids(uow: UnitOfWork, root_id: str) -> list[str]:
    """root + children + grandchildren (epic->feature->task is the deepest hierarchy)."""
    ids = [root_id]
    children = uow.work_items.list(filters={"parent_id": root_id}, page_size=1000).results
    ids += [c.id for c in children]
    for child in children:
        grand = uow.work_items.list(filters={"parent_id": child.id}, page_size=1000).results
        ids += [g.id for g in grand]
    return ids


@router.get("/work-items/{item_id}/usage")
def work_item_usage(
    item_id: str,
    group_by: str | None = Query(default=None),
    uow: UnitOfWork = Depends(get_uow),
) -> dict:
    _validate_group(group_by)
    with uow.transaction():
        uow.work_items.get(item_id)  # 404 / owner scope
        ids = _descendant_ids(uow, item_id)
        records = uow.usage.list(filters={"work_item_id__in": ids}, page_size=10000).results
    return ok(_payload(records, group_by))


@router.get("/projects/{project_id}/usage")
def project_usage(
    project_id: str,
    group_by: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    uow: UnitOfWork = Depends(get_uow),
) -> dict:
    _validate_group(group_by)
    if since and until and since > until:
        raise HTTPException(status_code=422, detail="since must be <= until")
    filters: dict = {"project_id": project_id}
    if since:
        filters["created_at__gte"] = since
    if until:
        filters["created_at__lte"] = until
    with uow.transaction():
        uow.projects.get(project_id)  # 404 / owner scope
        records = uow.usage.list(filters=filters, page_size=10000).results
    return ok(_payload(records, group_by))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_usage_api.py -v`
Expected: PASS (all cases). Then the full suite + coverage gate:
`uv run pytest` then `make coverage`.

- [ ] **Step 5: Commit**

```bash
git add src/interactors/api/routes/usage.py tests/integration/test_usage_api.py
git commit -m "feat: work-item (recursive) + project usage rollups"
```

---

## Self-Review

**Spec coverage** (`docs/specs/2026-06-13-a5d-usage-tracking-design.md`):
- §5 `TokenUsage` + helpers → Task 1. `StageResult.usage`/`model_usage` → Task 2.
- §6 parser captures `usage`/`modelUsage`, multi-model split, missing-usage tolerance → Task 3; fake → Task 4.
- §7 `UsageRecord` + `Run` counters + table + repo/uow/ports → Tasks 5–7.
- §8 `record_usage` writer, idempotency key, counter recompute, `run_stage` hook → Task 8.
- §9 three read endpoints + `group_by` + time window → Tasks 9–10.
- §10 error handling: missing usage (Task 3 test), 422 on bad `group_by`/window (Task 10).
- §11 testing across domain/parser/repo/workflow/API → covered per task.
- §2 out-of-scope (budgets, dashboards, pricing tables) → not implemented, as intended.

**Placeholder scan:** No TBD/TODO; every code step shows full code. Import edits that say
"...existing names..." refer to keeping the file's current imports and adding the named ones —
the new names are explicit.

**Type consistency:** `TokenUsage`, `StageResult.usage`/`model_usage`, `UsageRecord` fields,
the `record_usage` payload keys (`model_usage`, `agent_role`, `stage`), and the route
`group_by` keys (`stage`/`agent_role`/`model`) are consistent across tasks. `dedupe_key` is a
DTO property and a stored column, reconciled by the repository override in Task 7.

**Cost authority note:** `Run.cost_usd` stays owned by the workflow's existing accumulation
(`workflows.py:119-120`); `record_usage` only writes rows + token counters. Per-row `cost_usd`
is the rollup source of truth; the two reconcile because the workflow sums the same per-stage
`StageResult.cost_usd` the rows carry.
