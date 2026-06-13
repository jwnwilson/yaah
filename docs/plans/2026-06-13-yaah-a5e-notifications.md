# A5e Notification System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-class `Notification` entity and an owner-scoped inbox, raised by both the pipeline (gate opened / run blocked / run failed) and the lead agent (in-band `yaah_notify` capability), delivered in-app behind a pluggable channel port, with gates auto-resolving their notifications.

**Architecture:** A pure `notification_for_event` policy maps `run_events` to notifications; a new `notification` `AgentEvent` carries agent-raised flags parsed from the runtime's `yaah_notify` tool-call; a `NotificationDispatcher` + `NotificationChannel` port handles delivery (in-app = persistence now); Temporal activities persist both producers' notifications and auto-resolve gate notifications on `gate_resolved`; an owner-scoped inbox API + a board-header bell expose them.

**Tech Stack:** Python 3.12, Pydantic v2, SQLAlchemy 2.0 (sync), FastAPI, Temporal (`temporalio`), pytest; UI: React + Vite + Tailwind + Vitest/MSW. Spec: `docs/specs/2026-06-13-a5e-notifications-design.md`. **Depends on A5d only for the deferred budget-threshold trigger (not built here).**

---

## File Structure

- `src/domain/models.py` — **modify**. `Notification` DTO + `NotificationCategory`/`Severity`/`Source` enums + `NotificationAction`.
- `src/domain/notifications.py` — **create**. Pure `notification_for_event` + `resolves` policy.
- `src/domain/runtime.py` — **modify**. `AgentEvent.type` gains `"notification"`.
- `src/adapters/runtime/stream_json.py` — **modify**. Recognise the `yaah_notify` tool-call.
- `src/adapters/database/orm.py` — **modify**. `NotificationRow`.
- `src/adapters/database/repositories.py` — **modify**. `NotificationRepository`.
- `src/adapters/database/uow.py` — **modify**. `uow.notifications`.
- `src/adapters/database/ports.py` — **modify**. `notifications` on `UnitOfWork`.
- `src/adapters/notify/ports.py` — **create**. `NotificationChannel` Protocol + `NotificationDispatcher`.
- `src/adapters/notify/inapp.py` — **create**. `InAppChannel` (no-op) + `FakeChannel` (test).
- `src/interactors/temporal/activities.py` — **modify**. System notifications + auto-resolve + agent-notification persistence + `record_notification` activity + `notifier` dependency.
- `src/interactors/temporal/worker.py` — **modify**. Build dispatcher, pass to `RunActivities`, register `record_notification`.
- `src/interactors/api/routes/notifications.py` — **create**. Inbox API.
- `src/interactors/api/app.py` — **modify**. Register the notifications router.
- `ui/src/features/notifications/*` — **create**. Bell + hook (Task 10).
- Tests under `tests/unit/`, `tests/integration/`, `tests/workflow/`, `ui/src/features/notifications/`.

---

## Task 1: `Notification` DTO + enums + `NotificationAction`

**Files:**
- Modify: `src/domain/models.py`
- Test: `tests/unit/test_notification_dto.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_notification_dto.py
from domain.models import (
    Notification, NotificationAction, NotificationCategory, NotificationSeverity,
    NotificationSource,
)


def test_notification_defaults():
    n = Notification(owner_id="dev-user", source=NotificationSource.SYSTEM,
                     category=NotificationCategory.ALERT, title="run failed")
    assert n.id and len(n.id) == 32
    assert n.severity == NotificationSeverity.INFO
    assert n.read_at is None and n.resolved_at is None
    assert n.action is None


def test_notification_with_gate_action():
    n = Notification(owner_id="u", source=NotificationSource.SYSTEM,
                     category=NotificationCategory.REVIEW, severity=NotificationSeverity.ATTENTION,
                     title="plan ready", run_id="r1",
                     action=NotificationAction(kind="gate_approval", run_id="r1"))
    assert n.action.kind == "gate_approval"
    assert n.action.run_id == "r1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_notification_dto.py -v`
Expected: FAIL — names not defined in `domain.models`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/domain/models.py` (the file already imports `StrEnum`, `Literal`, `BaseModel`,
`Field`, `datetime`, `new_id`, `utc_now`):

```python
class NotificationCategory(StrEnum):
    DECISION = "decision"
    REVIEW = "review"
    UPDATE = "update"
    ALERT = "alert"


class NotificationSeverity(StrEnum):
    INFO = "info"
    ATTENTION = "attention"
    CRITICAL = "critical"


class NotificationSource(StrEnum):
    AGENT = "agent"
    SYSTEM = "system"


class NotificationAction(BaseModel):
    kind: Literal["gate_approval"]
    run_id: str


class Notification(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    source: NotificationSource
    category: NotificationCategory
    severity: NotificationSeverity = NotificationSeverity.INFO
    title: str
    body: str = ""
    run_id: str | None = None
    work_item_id: str | None = None
    project_id: str | None = None
    action: NotificationAction | None = None
    read_at: datetime | None = None
    resolved_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_notification_dto.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/domain/models.py tests/unit/test_notification_dto.py
git commit -m "feat: Notification DTO + category/severity/source enums + action"
```

---

## Task 2: Pure `notification_for_event` + `resolves` policy

**Files:**
- Create: `src/domain/notifications.py`
- Test: `tests/unit/test_notifications_policy.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_notifications_policy.py
from domain.models import (
    Notification, NotificationAction, NotificationCategory, NotificationSeverity,
    NotificationSource, Run, RunEvent, RunEventType, RunStage,
)
from domain.notifications import notification_for_event, resolves


def _run():
    return Run(id="r1", owner_id="dev-user", task_id="t1", team_id="tm")


def _event(type_, stage=RunStage.PLAN):
    return RunEvent(run_id="r1", owner_id="dev-user", stage=stage, type=type_)


def test_gate_opened_maps_to_review_action_required():
    n = notification_for_event(_event(RunEventType.GATE_OPENED), run=_run())
    assert n is not None
    assert n.category == NotificationCategory.REVIEW
    assert n.severity == NotificationSeverity.ATTENTION
    assert n.source == NotificationSource.SYSTEM
    assert n.action == NotificationAction(kind="gate_approval", run_id="r1")
    assert n.run_id == "r1" and n.work_item_id == "t1"


def test_blocked_maps_to_attention_alert():
    n = notification_for_event(_event(RunEventType.BLOCKED), run=_run())
    assert n.category == NotificationCategory.ALERT
    assert n.severity == NotificationSeverity.ATTENTION
    assert n.action is None


def test_error_maps_to_critical_alert():
    n = notification_for_event(_event(RunEventType.ERROR), run=_run())
    assert n.category == NotificationCategory.ALERT
    assert n.severity == NotificationSeverity.CRITICAL


def test_unmapped_event_returns_none():
    assert notification_for_event(_event(RunEventType.STAGE_STARTED), run=_run()) is None
    assert notification_for_event(_event(RunEventType.AGENT_EVENT), run=_run()) is None


def test_resolves_matches_gate_resolved_for_same_run():
    n = Notification(owner_id="u", source=NotificationSource.SYSTEM,
                     category=NotificationCategory.REVIEW, title="x", run_id="r1",
                     action=NotificationAction(kind="gate_approval", run_id="r1"))
    assert resolves(n, _event(RunEventType.GATE_RESOLVED)) is True
    assert resolves(n, _event(RunEventType.BLOCKED)) is False
    n_no_action = n.model_copy(update={"action": None})
    assert resolves(n_no_action, _event(RunEventType.GATE_RESOLVED)) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_notifications_policy.py -v`
Expected: FAIL — `domain.notifications` does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
# src/domain/notifications.py
"""Pure policy mapping run events to notifications (no I/O)."""

from domain.models import (
    Notification,
    NotificationAction,
    NotificationCategory,
    NotificationSeverity,
    NotificationSource,
    Run,
    RunEvent,
    RunEventType,
)


def notification_for_event(ev: RunEvent, *, run: Run) -> Notification | None:
    """Map a structural run event to a system notification, or None if it isn't
    user-facing. Pure: never raises on unmapped types."""
    common = dict(
        owner_id=run.owner_id,
        source=NotificationSource.SYSTEM,
        run_id=run.id,
        work_item_id=run.task_id,
    )
    if ev.type == RunEventType.GATE_OPENED:
        return Notification(
            category=NotificationCategory.REVIEW,
            severity=NotificationSeverity.ATTENTION,
            title="Approval needed",
            body=f"A run reached the {ev.stage} gate and needs your approval.",
            action=NotificationAction(kind="gate_approval", run_id=run.id),
            **common,
        )
    if ev.type == RunEventType.BLOCKED:
        return Notification(
            category=NotificationCategory.ALERT,
            severity=NotificationSeverity.ATTENTION,
            title="Run blocked",
            body=ev.message or f"A run blocked at {ev.stage}.",
            **common,
        )
    if ev.type == RunEventType.ERROR:
        return Notification(
            category=NotificationCategory.ALERT,
            severity=NotificationSeverity.CRITICAL,
            title="Run failed",
            body=ev.message or f"A run errored at {ev.stage}.",
            **common,
        )
    return None


def resolves(notification: Notification, ev: RunEvent) -> bool:
    """True when this event resolves the (action-required) notification."""
    return (
        ev.type == RunEventType.GATE_RESOLVED
        and notification.action is not None
        and notification.action.run_id == ev.run_id
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_notifications_policy.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/domain/notifications.py tests/unit/test_notifications_policy.py
git commit -m "feat: pure notification_for_event + resolves policy"
```

---

## Task 3: `AgentEvent` gains the `notification` type

**Files:**
- Modify: `src/domain/runtime.py`
- Test: `tests/unit/test_agent_event_notification.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_agent_event_notification.py
from domain.models import RunStage
from domain.runtime import AgentEvent


def test_agent_event_accepts_notification_type():
    ev = AgentEvent(type="notification", stage=RunStage.IMPLEMENT,
                    message="chose Postgres",
                    data={"category": "decision", "title": "DB choice",
                          "body": "Postgres over SQLite", "severity": "info"})
    assert ev.type == "notification"
    assert ev.data["category"] == "decision"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_agent_event_notification.py -v`
Expected: FAIL — `"notification"` is not in the `AgentEvent.type` Literal.

- [ ] **Step 3: Write minimal implementation**

In `src/domain/runtime.py`, extend the `AgentEvent.type` Literal:

```python
class AgentEvent(BaseModel):
    type: Literal["progress", "heartbeat", "artifact", "result", "notification"]
    stage: RunStage
    message: str = ""
    data: dict = {}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_agent_event_notification.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/domain/runtime.py tests/unit/test_agent_event_notification.py
git commit -m "feat: AgentEvent supports notification type"
```

---

## Task 4: Parse the `yaah_notify` tool-call into a notification event

The Claude Code stream emits assistant messages whose `content` array can contain
`{"type": "tool_use", "name": "yaah_notify", "input": {...}}` blocks. Recognise that tool by
name and emit an `AgentEvent(type="notification")`.

**Files:**
- Modify: `src/adapters/runtime/stream_json.py`
- Test: `tests/unit/test_stream_json_notification.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_stream_json_notification.py
import json

from adapters.runtime import stream_json
from domain.models import RunStage


def test_yaah_notify_tool_use_becomes_notification_event():
    line = json.dumps({
        "type": "assistant",
        "message": {"content": [
            {"type": "text", "text": "I'll flag this."},
            {"type": "tool_use", "name": "yaah_notify",
             "input": {"category": "decision", "title": "DB choice",
                       "body": "Postgres over SQLite", "severity": "info"}},
        ]},
    })
    events, _result = stream_json.parse([line], RunStage.IMPLEMENT)
    notifs = [e for e in events if e.type == "notification"]
    assert len(notifs) == 1
    assert notifs[0].data["title"] == "DB choice"
    assert notifs[0].message == "DB choice"


def test_malformed_yaah_notify_missing_title_is_dropped():
    line = json.dumps({
        "type": "assistant",
        "message": {"content": [
            {"type": "tool_use", "name": "yaah_notify", "input": {"category": "decision"}},
        ]},
    })
    events, _result = stream_json.parse([line], RunStage.IMPLEMENT)
    assert [e for e in events if e.type == "notification"] == []


def test_other_tool_use_is_ignored():
    line = json.dumps({
        "type": "assistant",
        "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
        ]},
    })
    events, _result = stream_json.parse([line], RunStage.IMPLEMENT)
    assert [e for e in events if e.type == "notification"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_stream_json_notification.py -v`
Expected: FAIL — no notification events produced.

- [ ] **Step 3: Write minimal implementation**

In `src/adapters/runtime/stream_json.py`, add a helper after `_assistant_text`:

```python
_NOTIFY_TOOL = "yaah_notify"


def _notification_events(obj: dict, stage: RunStage) -> list[AgentEvent]:
    content = obj.get("message", {}).get("content", [])
    out: list[AgentEvent] = []
    for p in content:
        if not isinstance(p, dict) or p.get("type") != "tool_use" or p.get("name") != _NOTIFY_TOOL:
            continue
        data = p.get("input") or {}
        title = str(data.get("title") or "").strip()
        if not title:
            continue  # malformed: drop (Task 8 keeps the normal agent_event trail)
        out.append(AgentEvent(type="notification", stage=stage, message=title[:200], data=data))
    return out
```

In the `assistant` branch of `parse`, after appending the progress event, also append the
notification events:

```python
        if kind == "assistant":
            text = _assistant_text(obj)
            if text:
                events.append(AgentEvent(type="progress", stage=stage, message=text[:500]))
            events.extend(_notification_events(obj, stage))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_stream_json_notification.py -v`
Expected: PASS (3 tests). Confirm no regression: `uv run pytest tests/ -k stream -v`.

- [ ] **Step 5: Commit**

```bash
git add src/adapters/runtime/stream_json.py tests/unit/test_stream_json_notification.py
git commit -m "feat: parse yaah_notify tool-call into notification events"
```

---

## Task 5: `NotificationRow` ORM

**Files:**
- Modify: `src/adapters/database/orm.py`
- Test: `tests/unit/test_notification_orm.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_notification_orm.py
from sqlalchemy import create_engine, inspect

from adapters.database.orm import Base


def test_notifications_table_columns():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("notifications")}
    assert {"id", "owner_id", "source", "category", "severity", "title", "body",
            "run_id", "work_item_id", "project_id", "action", "read_at", "resolved_at",
            "created_at"} <= cols
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_notification_orm.py -v`
Expected: FAIL — `notifications` table absent.

- [ ] **Step 3: Write minimal implementation**

Append to `src/adapters/database/orm.py` (`JSON`, `DateTime`, `String`, `Text` are already
imported):

```python
class NotificationRow(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="info")
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    run_id: Mapped[str | None] = mapped_column(String(32), index=True)
    work_item_id: Mapped[str | None] = mapped_column(String(32))
    project_id: Mapped[str | None] = mapped_column(String(32))
    action: Mapped[dict | None] = mapped_column(JSON)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_notification_orm.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/adapters/database/orm.py tests/unit/test_notification_orm.py
git commit -m "feat: notifications table"
```

---

## Task 6: `NotificationRepository` + `uow.notifications` + ports

The generic `SqlRepository` handles this entity directly: `action` is a Pydantic field that
maps to the `action` JSON column (dict ↔ model), and read/resolve are normal updates.

**Files:**
- Modify: `src/adapters/database/repositories.py`
- Modify: `src/adapters/database/uow.py`
- Modify: `src/adapters/database/ports.py`
- Test: `tests/unit/test_notification_repository.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_notification_repository.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.models import (
    Notification, NotificationAction, NotificationCategory, NotificationSource, utc_now,
)


@pytest.fixture
def factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _n(**kw):
    base = dict(owner_id="dev-user", source=NotificationSource.SYSTEM,
                category=NotificationCategory.ALERT, title="t")
    base.update(kw)
    return Notification(**base)


def test_create_list_and_mark_read(factory):
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        created = uow.notifications.create(_n(run_id="r1"))
        uow.notifications.update(created.id, created.model_copy(update={"read_at": utc_now()}))
        fetched = uow.notifications.get(created.id)
    assert fetched.read_at is not None


def test_action_round_trips(factory):
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        created = uow.notifications.create(
            _n(category=NotificationCategory.REVIEW, run_id="r1",
               action=NotificationAction(kind="gate_approval", run_id="r1")))
        fetched = uow.notifications.get(created.id)
    assert fetched.action is not None and fetched.action.run_id == "r1"


def test_owner_scoping(factory):
    a = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with a.transaction():
        a.notifications.create(_n())
    b = SqlUnitOfWork(factory, required_filters={"owner_id": "other"})
    with b.transaction():
        assert b.notifications.list().total == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_notification_repository.py -v`
Expected: FAIL — `uow.notifications` does not exist.

- [ ] **Step 3: Write minimal implementation**

`src/adapters/database/repositories.py` — add to the imports and a subclass:

```python
from adapters.database.orm import (
    # ...existing names...
    NotificationRow,
)
from domain.models import (
    # ...existing names...
    Notification,
)


class NotificationRepository(SqlRepository[Notification]):
    orm_model = NotificationRow
    dto = Notification
```

`src/adapters/database/uow.py` — add `NotificationRepository` to the repositories import and a
property:

```python
    @property
    def notifications(self) -> NotificationRepository:
        return NotificationRepository(self.session, self._required_filters)
```

`src/adapters/database/ports.py` — add `Notification` to the `domain.models` import and a
property on the `UnitOfWork` Protocol:

```python
    @property
    def notifications(self) -> Repository[Notification]: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_notification_repository.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/adapters/database/repositories.py src/adapters/database/uow.py src/adapters/database/ports.py tests/unit/test_notification_repository.py
git commit -m "feat: NotificationRepository + uow.notifications + ports"
```

---

## Task 7: `NotificationChannel` port + `NotificationDispatcher` + in-app/fake channels

**Files:**
- Create: `src/adapters/notify/__init__.py` (empty)
- Create: `src/adapters/notify/ports.py`
- Create: `src/adapters/notify/inapp.py`
- Test: `tests/unit/test_notification_dispatcher.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_notification_dispatcher.py
from adapters.notify.inapp import FakeChannel, InAppChannel
from adapters.notify.ports import NotificationDispatcher
from domain.models import Notification, NotificationCategory, NotificationSource


def _n():
    return Notification(owner_id="u", source=NotificationSource.SYSTEM,
                        category=NotificationCategory.ALERT, title="t")


def test_dispatcher_delivers_to_all_channels():
    fake = FakeChannel()
    NotificationDispatcher([InAppChannel(), fake]).deliver(_n())
    assert len(fake.delivered) == 1


def test_dispatcher_swallows_channel_errors():
    class Boom:
        def deliver(self, n):
            raise RuntimeError("smtp down")

    fake = FakeChannel()
    # a throwing channel must not prevent later channels from receiving the notification
    NotificationDispatcher([Boom(), fake]).deliver(_n())
    assert len(fake.delivered) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_notification_dispatcher.py -v`
Expected: FAIL — `adapters.notify` does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
# src/adapters/notify/ports.py
import logging
from typing import Protocol

from domain.models import Notification

logger = logging.getLogger(__name__)


class NotificationChannel(Protocol):
    def deliver(self, n: Notification) -> None: ...


class NotificationDispatcher:
    """Fans an (already-persisted) notification out to external channels. In-app delivery
    IS persistence, so the in-app channel is a no-op. A channel failure is logged and
    swallowed so it never loses the inbox item or fails a run."""

    def __init__(self, channels: list[NotificationChannel]):
        self._channels = channels

    def deliver(self, n: Notification) -> None:
        for channel in self._channels:
            try:
                channel.deliver(n)
            except Exception:  # noqa: BLE001 - delivery is best-effort
                logger.exception("notification channel %s failed", type(channel).__name__)
```

```python
# src/adapters/notify/inapp.py
from domain.models import Notification


class InAppChannel:
    """The inbox itself is the in-app channel; persistence is the delivery, so deliver
    is a no-op."""

    def deliver(self, n: Notification) -> None:
        return None


class FakeChannel:
    """Records delivered notifications (test double for external channels)."""

    def __init__(self) -> None:
        self.delivered: list[Notification] = []

    def deliver(self, n: Notification) -> None:
        self.delivered.append(n)
```

Create an empty `src/adapters/notify/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_notification_dispatcher.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/adapters/notify/ tests/unit/test_notification_dispatcher.py
git commit -m "feat: NotificationChannel port + dispatcher + in-app/fake channels"
```

---

## Task 8: Wire producers into the activities (system + agent) + auto-resolve

`record_event` gains: after persisting the run_event, persist a system notification (if the
event maps to one), guarding against duplicate open gate notifications; and on `gate_resolved`,
resolve the run's open action-required notifications. `run_stage` persists agent `notification`
events. A new `record_notification` activity handles agent-raised flags. `RunActivities` gains
an optional `notifier` (a `NotificationDispatcher`).

**Files:**
- Modify: `src/interactors/temporal/activities.py`
- Modify: `src/interactors/temporal/worker.py`
- Test: `tests/workflow/test_notifications_activity.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/workflow/test_notifications_activity.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from adapters.notify.inapp import FakeChannel
from adapters.notify.ports import NotificationDispatcher
from domain.models import (
    NotificationCategory, Project, Run, RunEventType, WorkItem, WorkItemKind, WorkItemStatus,
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
        uow.projects.create(Project(id="p1", owner_id="dev-user", name="P", local_path="/x"))
        uow.work_items.create(WorkItem(id="t1", owner_id="dev-user", project_id="p1",
                                       kind=WorkItemKind.TASK, parent_id="f1", title="T",
                                       status=WorkItemStatus.IN_PROGRESS))
        uow.runs.create(Run(id="r1", owner_id="dev-user", task_id="t1", team_id="tm"))


def _acts(factory, fake):
    return RunActivities(factory, runtime=None, storage=None, git=None, forge=None,
                         notifier=NotificationDispatcher([fake]))


def test_gate_opened_event_creates_action_required_notification(factory):
    _seed(factory)
    fake = FakeChannel()
    acts = _acts(factory, fake)
    acts.record_event({"run_id": "r1", "owner_id": "dev-user", "stage": "plan",
                       "type": RunEventType.GATE_OPENED, "message": ""})
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        notifs = uow.notifications.list(filters={"run_id": "r1"}).results
    assert len(notifs) == 1
    assert notifs[0].category == NotificationCategory.REVIEW
    assert notifs[0].action is not None
    assert len(fake.delivered) == 1


def test_duplicate_gate_opened_does_not_stack(factory):
    _seed(factory)
    acts = _acts(factory, FakeChannel())
    payload = {"run_id": "r1", "owner_id": "dev-user", "stage": "plan",
               "type": RunEventType.GATE_OPENED, "message": ""}
    acts.record_event(payload)
    acts.record_event(payload)  # resume / retry
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        assert uow.notifications.list(filters={"run_id": "r1"}).total == 1


def test_gate_resolved_auto_resolves_open_notification(factory):
    _seed(factory)
    acts = _acts(factory, FakeChannel())
    acts.record_event({"run_id": "r1", "owner_id": "dev-user", "stage": "plan",
                       "type": RunEventType.GATE_OPENED, "message": ""})
    acts.record_event({"run_id": "r1", "owner_id": "dev-user", "stage": "plan",
                       "type": RunEventType.GATE_RESOLVED, "message": "approved"})
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        notif = uow.notifications.list(filters={"run_id": "r1"}).results[0]
    assert notif.resolved_at is not None


def test_record_notification_persists_agent_flag(factory):
    _seed(factory)
    fake = FakeChannel()
    acts = _acts(factory, fake)
    acts.record_notification({"run_id": "r1", "owner_id": "dev-user",
                              "category": "decision", "title": "DB choice",
                              "body": "Postgres over SQLite", "severity": "info"})
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        notif = uow.notifications.list(filters={"run_id": "r1"}).results[0]
    assert notif.source.value == "agent"
    assert notif.category == NotificationCategory.DECISION
    assert notif.work_item_id == "t1"
    assert len(fake.delivered) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/workflow/test_notifications_activity.py -v`
Expected: FAIL — `RunActivities.__init__` has no `notifier`; no notification logic.

- [ ] **Step 3: Write minimal implementation**

In `src/interactors/temporal/activities.py`, extend imports:

```python
from adapters.notify.ports import NotificationDispatcher
from domain.models import (
    Notification, NotificationCategory, NotificationSeverity, NotificationSource,
    RunEvent, RunEventType, RunStage, RunStatus, utc_now,
)
from domain.notifications import notification_for_event, resolves
```

Add `notifier` to the constructor (default builds an empty dispatcher so existing callers and
tests that omit it keep working):

```python
    def __init__(self, session_factory, runtime: AgentRuntime, storage: StoragePort,
                 git, forge, notifier: NotificationDispatcher | None = None) -> None:
        self._session_factory = session_factory
        self._runtime = runtime
        self._storage = storage
        self._git = git
        self._forge = forge
        self._notifier = notifier or NotificationDispatcher([])
```

Replace `record_event` so it also raises/resolves notifications inside the same transaction,
then delivers after commit:

```python
    @activity.defn(name="record_event")
    def record_event(self, payload: dict) -> None:
        owner_id = payload["owner_id"]
        run_id = payload["run_id"]
        ev_type = RunEventType(payload["type"])
        stage = RunStage(payload["stage"]) if payload.get("stage") else None
        to_deliver: list[Notification] = []
        uow = self._uow(owner_id)
        with uow.transaction():
            ev = RunEvent(run_id=run_id, owner_id=owner_id, stage=stage, type=ev_type,
                          message=payload.get("message", ""), created_at=utc_now())
            uow.run_events.create(ev)

            if ev_type == RunEventType.GATE_RESOLVED:
                open_notifs = uow.notifications.list(
                    filters={"run_id": run_id, "resolved_at__isnull": True}, page_size=200
                ).results
                for n in open_notifs:
                    if resolves(n, ev):
                        uow.notifications.update(
                            n.id, n.model_copy(update={"resolved_at": utc_now()}))
            else:
                run = uow.runs.get(run_id)
                notif = notification_for_event(ev, run=run)
                if notif is not None and not self._has_open_gate_notification(uow, run_id, notif):
                    to_deliver.append(uow.notifications.create(notif))
        for n in to_deliver:
            self._notifier.deliver(n)

    def _has_open_gate_notification(self, uow, run_id: str, candidate: Notification) -> bool:
        """Prevent duplicate open action-required notifications on resume."""
        if candidate.action is None:
            return False
        existing = uow.notifications.list(
            filters={"run_id": run_id, "resolved_at__isnull": True}, page_size=200
        ).results
        return any(n.action is not None for n in existing)
```

Add the agent-notification activity:

```python
    @activity.defn(name="record_notification")
    def record_notification(self, payload: dict) -> None:
        owner_id = payload["owner_id"]
        run_id = payload["run_id"]
        category = NotificationCategory(payload.get("category", "update"))
        severity = NotificationSeverity(payload.get("severity", "info"))
        to_deliver: list[Notification] = []
        uow = self._uow(owner_id)
        with uow.transaction():
            run = uow.runs.get(run_id)
            notif = Notification(
                owner_id=owner_id, source=NotificationSource.AGENT, category=category,
                severity=severity, title=payload["title"], body=payload.get("body", ""),
                run_id=run_id, work_item_id=run.task_id,
            )
            to_deliver.append(uow.notifications.create(notif))
        for n in to_deliver:
            self._notifier.deliver(n)
```

In `run_stage`, branch the event loop so agent `notification` events are persisted as
notifications and everything else stays an `agent_event`:

```python
        for event in self._runtime.run_stage(ctx):
            events.append(event)
            _heartbeat(event.message)
            if event.type == "notification" and event.data.get("title"):
                self.record_notification({
                    "run_id": payload["run_id"], "owner_id": payload["owner_id"],
                    "category": event.data.get("category", "update"),
                    "severity": event.data.get("severity", "info"),
                    "title": event.data["title"], "body": event.data.get("body", ""),
                })
            else:
                self.record_event({
                    "run_id": payload["run_id"], "owner_id": payload["owner_id"],
                    "stage": payload["stage"], "type": RunEventType.AGENT_EVENT,
                    "message": event.message,
                })
```

> If the A5d plan was implemented first, keep its `result = result_of(events)` / `record_usage`
> tail after this loop; this task only changes how individual events are persisted inside the
> loop.

In `src/interactors/temporal/worker.py`: build a dispatcher, pass it to `RunActivities`, and
register `record_notification`:

```python
    from adapters.notify.inapp import InAppChannel
    from adapters.notify.ports import NotificationDispatcher
    notifier = NotificationDispatcher([InAppChannel()])  # external channels added later
    acts = RunActivities(factory, runtime, storage, git, forge, notifier=notifier)
    return [acts.persist_run_state, acts.record_event, acts.record_notification,
            acts.run_stage, acts.cleanup_workspace, acts.provision_workspace, acts.open_pr]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/workflow/test_notifications_activity.py -v`
Expected: PASS (4 tests). Then the full workflow suite to confirm the `record_event` refactor
didn't break the pipeline: `uv run pytest tests/workflow/ -v`.

- [ ] **Step 5: Commit**

```bash
git add src/interactors/temporal/activities.py src/interactors/temporal/worker.py tests/workflow/test_notifications_activity.py
git commit -m "feat: pipeline + agent notification producers with gate auto-resolve"
```

---

## Task 9: Inbox API — list, unread-count, mark read/resolve

**Files:**
- Create: `src/interactors/api/routes/notifications.py`
- Modify: `src/interactors/api/app.py`
- Test: `tests/integration/test_notifications_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_notifications_api.py
from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def _client():
    return TestClient(create_app(Settings(database_url="sqlite://", auth_mode="dev")))


def _seed(client, **over):
    from adapters.database.uow import SqlUnitOfWork
    from domain.models import Notification, NotificationCategory, NotificationSource
    uow = SqlUnitOfWork(client.app.state.session_factory,
                        required_filters={"owner_id": "dev-user"})
    payload = dict(owner_id="dev-user", source=NotificationSource.SYSTEM,
                   category=NotificationCategory.ALERT, title="run failed", run_id="r1")
    payload.update(over)
    with uow.transaction():
        return uow.notifications.create(Notification(**payload)).id


def test_list_and_unread_count():
    client = _client()
    _seed(client)
    _seed(client, category="update", title="progress")
    assert len(client.get("/notifications").json()["data"]) == 2
    assert client.get("/notifications/unread-count").json()["data"]["count"] == 2


def test_filter_by_category():
    client = _client()
    _seed(client)
    _seed(client, category="update", title="progress")
    only_alert = client.get("/notifications", params={"category": "alert"}).json()["data"]
    assert len(only_alert) == 1 and only_alert[0]["category"] == "alert"


def test_mark_read_then_resolve_updates_unread_count():
    client = _client()
    nid = _seed(client)
    assert client.patch(f"/notifications/{nid}", json={"read": True}).status_code == 200
    assert client.get("/notifications/unread-count").json()["data"]["count"] == 0
    resolved = client.patch(f"/notifications/{nid}", json={"resolved": True}).json()["data"]
    assert resolved["resolved_at"] is not None
    assert len(client.get("/notifications", params={"status": "resolved"}).json()["data"]) == 1


def test_patch_unknown_id_is_404():
    client = _client()
    assert client.patch("/notifications/nope", json={"read": True}).status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_notifications_api.py -v`
Expected: FAIL — routes not registered.

- [ ] **Step 3: Write minimal implementation**

```python
# src/interactors/api/routes/notifications.py
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from adapters.database.ports import UnitOfWork
from domain.models import Notification, utc_now
from interactors.api.deps import get_uow
from interactors.api.envelope import ok

router = APIRouter(tags=["notifications"])

_STATUS = {"unread", "read", "resolved"}


def _status_filters(status: str | None) -> dict:
    if status == "unread":
        return {"read_at__isnull": True}
    if status == "read":
        return {"read_at__isnull": False, "resolved_at__isnull": True}
    if status == "resolved":
        return {"resolved_at__isnull": False}
    return {}


@router.get("/notifications")
def list_notifications(
    category: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page_size: int = Query(default=50),
    page_number: int = Query(default=1),
    uow: UnitOfWork = Depends(get_uow),
) -> dict:
    filters: dict = _status_filters(status if status in _STATUS else None)
    if category:
        filters["category"] = category
    with uow.transaction():
        page = uow.notifications.list(filters=filters, page_size=page_size,
                                      page_number=page_number, order_by="-created_at")
    return ok(
        [n.model_dump(mode="json") for n in page.results],
        meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number},
    )


@router.get("/notifications/unread-count")
def unread_count(uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        page = uow.notifications.list(filters={"read_at__isnull": True}, page_size=1)
    return ok({"count": page.total})


class PatchNotification(BaseModel):
    read: bool | None = None
    resolved: bool | None = None


@router.patch("/notifications/{notification_id}")
def patch_notification(
    notification_id: str, body: PatchNotification, uow: UnitOfWork = Depends(get_uow)
) -> dict:
    with uow.transaction():
        n: Notification = uow.notifications.get(notification_id)  # 404 / owner scope
        updates: dict = {}
        if body.read and n.read_at is None:
            updates["read_at"] = utc_now()
        if body.resolved and n.resolved_at is None:
            updates["resolved_at"] = utc_now()
            if n.read_at is None:
                updates["read_at"] = utc_now()
        result = uow.notifications.update(notification_id, n.model_copy(update=updates))
    return ok(result.model_dump(mode="json"))
```

Register in `src/interactors/api/app.py`: add `notifications` to the route import line and
include it:

```python
    from interactors.api.routes import (
        agents, capabilities, notifications, projects, runs, teams, work_items,
    )
    # ...existing include_router calls...
    app.include_router(notifications.router)
```

> If the A5d plan was implemented first, the import line also includes `usage`; keep both.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_notifications_api.py -v`
Expected: PASS (4 tests). Then full suite + coverage: `uv run pytest` then `make coverage`.

- [ ] **Step 5: Commit**

```bash
git add src/interactors/api/routes/notifications.py src/interactors/api/app.py tests/integration/test_notifications_api.py
git commit -m "feat: notifications inbox API (list / unread-count / read / resolve)"
```

---

## Task 10: Board-header notification bell (UI)

Mirror the existing data-hook pattern (`ui/src/features/runs/useRuns.ts`) and the API client in
`ui/src/lib/api/client.ts`; test with the MSW handler pattern in `ui/src/test/handlers.ts`.

**Files:**
- Create: `ui/src/features/notifications/useNotifications.ts`
- Create: `ui/src/features/notifications/NotificationBell.tsx`
- Create: `ui/src/features/notifications/NotificationBell.test.tsx`
- Modify: `ui/src/features/board/BoardPage.tsx` (mount the bell in the header)
- Modify: `ui/src/test/handlers.ts` (add `/notifications` + `/notifications/unread-count` handlers)

- [ ] **Step 1: Write the failing test**

```tsx
// ui/src/features/notifications/NotificationBell.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { NotificationBell } from "./NotificationBell";
import { withProviders } from "../../test/withProviders"; // existing wrapper used by other feature tests

describe("NotificationBell", () => {
  it("shows the unread badge count from the API", async () => {
    render(withProviders(<NotificationBell />));
    expect(await screen.findByLabelText("2 unread notifications")).toBeInTheDocument();
  });
});
```

Add MSW handlers in `ui/src/test/handlers.ts` returning the envelope shape:

```ts
// inside the handlers array
http.get("/notifications/unread-count", () =>
  HttpResponse.json({ success: true, data: { count: 2 }, error: null }),
),
http.get("/notifications", () =>
  HttpResponse.json({
    success: true,
    data: [
      { id: "n1", category: "review", severity: "attention", title: "Approval needed",
        run_id: "r1", action: { kind: "gate_approval", run_id: "r1" },
        read_at: null, resolved_at: null },
    ],
    error: null,
    meta: { total: 1, page_size: 50, page_number: 1 },
  }),
),
```

> If your test wrapper has a different name than `withProviders`, use whichever wrapper the
> existing `*.test.tsx` files import (e.g. `renderWithClient`). Do not introduce a new wrapper.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npx vitest run src/features/notifications/NotificationBell.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```ts
// ui/src/features/notifications/useNotifications.ts
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api/client"; // same client the other hooks use

export type Notification = {
  id: string;
  category: "decision" | "review" | "update" | "alert";
  severity: "info" | "attention" | "critical";
  title: string;
  body?: string;
  run_id: string | null;
  action: { kind: "gate_approval"; run_id: string } | null;
  read_at: string | null;
  resolved_at: string | null;
};

export function useUnreadCount() {
  return useQuery({
    queryKey: ["notifications", "unread-count"],
    queryFn: async () => (await api.get<{ count: number }>("/notifications/unread-count")).count,
    refetchInterval: 15_000, // poll, matching the board's polling model (SSE deferred)
  });
}

export function useNotifications() {
  return useQuery({
    queryKey: ["notifications"],
    queryFn: async () => await api.get<Notification[]>("/notifications"),
  });
}
```

> `api.get` is assumed to unwrap the `{success,data,error}` envelope and return `data`, the same
> convention the existing `useRuns.ts`/`useBoardItems.ts` hooks use. If the client exposes a
> different helper, use that — do not introduce a second client.

```tsx
// ui/src/features/notifications/NotificationBell.tsx
import { useState } from "react";
import { useNotifications, useUnreadCount } from "./useNotifications";

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const { data: count = 0 } = useUnreadCount();
  const { data: items = [] } = useNotifications();

  return (
    <div className="relative">
      <button
        type="button"
        aria-label={`${count} unread notifications`}
        onClick={() => setOpen((v) => !v)}
        className="relative rounded p-2 hover:bg-slate-100"
      >
        <span aria-hidden>🔔</span>
        {count > 0 && (
          <span className="absolute -right-1 -top-1 rounded-full bg-red-600 px-1.5 text-xs text-white">
            {count}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-10 mt-2 w-80 rounded border bg-white shadow">
          {items.length === 0 && <p className="p-3 text-sm text-slate-500">Nothing here.</p>}
          <ul>
            {items.map((n) => (
              <li key={n.id} className="border-b p-3 last:border-0">
                <p className="text-xs uppercase text-slate-400">{n.category}</p>
                <p className="font-medium">{n.title}</p>
                {n.action?.kind === "gate_approval" && (
                  <a className="text-sm text-blue-600" href={`#/runs/${n.action.run_id}`}>
                    Review &amp; approve →
                  </a>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
```

Mount it in `ui/src/features/board/BoardPage.tsx`'s header next to the existing title/actions:

```tsx
import { NotificationBell } from "../notifications/NotificationBell";
// ...in the header JSX:
<NotificationBell />
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npx vitest run src/features/notifications/` then `cd ui && npm run build`
Expected: PASS; build succeeds.

- [ ] **Step 5: Commit**

```bash
git add ui/src/features/notifications/ ui/src/test/handlers.ts ui/src/features/board/BoardPage.tsx
git commit -m "feat: board-header notification bell with unread badge"
```

---

## Self-Review

**Spec coverage** (`docs/specs/2026-06-13-a5e-notifications-design.md`):
- §5 `Notification` DTO + enums + `NotificationAction` → Task 1; lifecycle (read/resolve) → Tasks 6 + 9.
- §5/§6 pure `notification_for_event` + `resolves` → Task 2.
- §6 agent in-band path: `notification` `AgentEvent` (Task 3) parsed from `yaah_notify` (Task 4), persisted by `run_stage`/`record_notification` (Task 8).
- §6 system path + §3 gate auto-resolve → Task 8 (`record_event` map + `gate_resolved` resolve).
- §7 dispatcher + channel port + in-app → Task 7; wired into activities → Task 8.
- §8 persistence (`NotificationRow`, repo, uow, ports) → Tasks 5–6.
- §9 inbox API (list/filter/unread-count/read/resolve; no public create) → Task 9.
- §10 board UI bell + badge + deep-link → Task 10.
- §11 error handling: total mapping (Task 2), swallowed channel errors (Task 7), malformed agent payload dropped (Task 4), idempotent resolve / 404 patch (Tasks 8–9).
- §2 out-of-scope (blocking gates, external channels, budget trigger, prefs) → not implemented, as intended.

**Placeholder scan:** No TBD/TODO; every backend code step shows full code. The UI task flags
the two things it can't verify from the spec (the exact `api.get` helper and test-wrapper
names) and tells the engineer to reuse the project's existing ones rather than invent new ones.

**Type consistency:** `Notification` fields, `NotificationAction.kind == "gate_approval"`, the
`record_notification` payload keys (`category`/`severity`/`title`/`body`), the parser `data`
keys (same set), and the API `status` values (`unread`/`read`/`resolved`) are consistent across
tasks. `notification_for_event(ev, *, run)` and `resolves(n, ev)` signatures match their call
sites in Task 8.

**Sequencing note:** Task 8 edits `record_event` and the `run_stage` event loop. If the A5d
plan is implemented in the same branch first, preserve its `result_of`/`record_usage` tail in
`run_stage` (called after the loop) — the two changes touch different parts of the method and
compose cleanly.
