# Messaging & Assignee Substrate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the durable `Message` entity (agent mailbox + UI inbox row) and a `WorkItem.assignee_agent_id` field — the data substrate the lead-driven orchestration engine writes to.

**Architecture:** Pure-domain Pydantic models (`domain/models.py`) + SQLAlchemy rows (`adapters/database/orm.py`) + a generic `SqlRepository` subclass wired through the owner-scoped `UnitOfWork`, plus one Alembic migration. No I/O in domain; owner scoping enforced by the UoW required-filters. Mirrors the existing `Notification` pattern exactly.

**Tech Stack:** Python 3.12, Pydantic v2, SQLAlchemy 2.0, Alembic, pytest (SQLite in-memory for unit/repo tests).

**Scope:** This is Plan 1 of 3 for the lead-orchestration foundation (see `docs/specs/2026-06-14-lead-orchestration-design.md` / ADR-0002). Plan 2 = orchestration domain & guards; Plan 3 = workflow & actors. New `RunEventType`s and the Temporal mechanics land in Plan 3 where they are emitted and tested. HTTP endpoints for messages/assignee are deferred to their consumers (Plan 3 + the UI spec).

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/domain/models.py` | `Message` + enums + validator; `WorkItem.assignee_agent_id` | Modify |
| `src/adapters/database/orm.py` | `MessageRow` table; `WorkItemRow.assignee_agent_id` column | Modify |
| `src/adapters/database/repositories.py` | `MessageRepository` | Modify |
| `src/adapters/database/ports.py` | `messages` on the `UnitOfWork` protocol | Modify |
| `src/adapters/database/uow.py` | `messages` property | Modify |
| `migrations/versions/orch1msg01_messages_and_assignee.py` | `messages` table + `work_items.assignee_agent_id` | Create |
| `tests/unit/test_message_model.py` | Message validation | Create |
| `tests/unit/test_message_repository.py` | Repo CRUD, owner scoping, mailbox filters, assignee | Create |

---

## Task 1: `Message` domain model

**Files:**
- Modify: `src/domain/models.py` (add after the `Notification` block, near line 252)
- Test: `tests/unit/test_message_model.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_message_model.py
import pytest

from domain.models import (
    Message,
    MessageKind,
    MessageRecipientKind,
    MessageSenderKind,
)


def test_agent_to_agent_message_is_valid():
    msg = Message(
        owner_id="dev-user",
        sender_kind=MessageSenderKind.AGENT,
        sender_agent_id="a-lead",
        recipient_kind=MessageRecipientKind.AGENT,
        recipient_agent_id="a-eng",
        kind=MessageKind.DISPATCH,
        body="implement the thing",
    )
    assert msg.id and len(msg.id) == 32
    assert msg.delivered_at is None and msg.processed_at is None and msg.read_at is None


def test_agent_sender_requires_sender_agent_id():
    with pytest.raises(ValueError, match="sender_agent_id"):
        Message(
            owner_id="dev-user",
            sender_kind=MessageSenderKind.AGENT,
            recipient_kind=MessageRecipientKind.USER,
            body="hi",
        )


def test_agent_recipient_requires_recipient_agent_id():
    with pytest.raises(ValueError, match="recipient_agent_id"):
        Message(
            owner_id="dev-user",
            sender_kind=MessageSenderKind.SYSTEM,
            recipient_kind=MessageRecipientKind.AGENT,
            body="hi",
        )


def test_system_to_user_message_needs_no_agent_ids():
    msg = Message(
        owner_id="dev-user",
        sender_kind=MessageSenderKind.SYSTEM,
        recipient_kind=MessageRecipientKind.USER,
        body="done",
    )
    assert msg.kind == MessageKind.CHAT  # default
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_message_model.py -v`
Expected: FAIL with `ImportError: cannot import name 'Message'`.

- [ ] **Step 3: Write minimal implementation**

Add to `src/domain/models.py` (after the `Notification` class). `StrEnum`, `BaseModel`, `Field`, `model_validator`, `datetime`, `new_id`, `utc_now` are already imported/used in this module.

```python
class MessageSenderKind(StrEnum):
    AGENT = "agent"
    SYSTEM = "system"
    USER = "user"


class MessageRecipientKind(StrEnum):
    AGENT = "agent"
    USER = "user"


class MessageKind(StrEnum):
    DISPATCH = "dispatch"   # lead -> worker work assignment
    REPORT = "report"       # worker -> lead result
    CHAT = "chat"           # peer-to-peer
    STATUS = "status"       # progress note


class Message(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    sender_kind: MessageSenderKind
    sender_agent_id: str | None = None
    recipient_kind: MessageRecipientKind
    recipient_agent_id: str | None = None
    kind: MessageKind = MessageKind.CHAT
    subject: str = ""
    body: str = ""
    run_id: str | None = None
    work_item_id: str | None = None
    project_id: str | None = None
    delivered_at: datetime | None = None
    processed_at: datetime | None = None
    read_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _identity_rules(self) -> "Message":
        if self.sender_kind == MessageSenderKind.AGENT and not self.sender_agent_id:
            raise ValueError("agent sender requires sender_agent_id")
        if self.recipient_kind == MessageRecipientKind.AGENT and not self.recipient_agent_id:
            raise ValueError("agent recipient requires recipient_agent_id")
        return self
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_message_model.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/domain/models.py tests/unit/test_message_model.py
git commit -m "feat: add Message domain model with identity validation"
```

---

## Task 2: `WorkItem.assignee_agent_id` field

**Files:**
- Modify: `src/domain/models.py` (the `WorkItem` class, ~line 66)
- Test: `tests/unit/test_message_model.py` (append — keeps assignee-default coverage with the new model surface)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_message_model.py`:

```python
def test_work_item_assignee_defaults_to_none():
    from domain.models import WorkItem, WorkItemKind

    item = WorkItem(
        owner_id="dev-user",
        project_id="p1",
        kind=WorkItemKind.EPIC,
        title="epic",
    )
    assert item.assignee_agent_id is None


def test_work_item_accepts_assignee():
    from domain.models import WorkItem, WorkItemKind

    item = WorkItem(
        owner_id="dev-user",
        project_id="p1",
        kind=WorkItemKind.EPIC,
        title="epic",
        assignee_agent_id="a-eng",
    )
    assert item.assignee_agent_id == "a-eng"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_message_model.py -k assignee -v`
Expected: FAIL — `WorkItem` has no field `assignee_agent_id` (`test_work_item_accepts_assignee` fails).

- [ ] **Step 3: Write minimal implementation**

In `src/domain/models.py`, add the field to `WorkItem` (immediately after the `status:` line and before `created_at:`):

```python
    assignee_agent_id: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_message_model.py -k assignee -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/domain/models.py tests/unit/test_message_model.py
git commit -m "feat: add assignee_agent_id to WorkItem"
```

---

## Task 3: `MessageRow` ORM + repository + UoW wiring

**Files:**
- Modify: `src/adapters/database/orm.py` (add `MessageRow`; add column to `WorkItemRow`)
- Modify: `src/adapters/database/repositories.py` (add `MessageRepository` + imports)
- Modify: `src/adapters/database/ports.py` (add `messages` to protocol + import)
- Modify: `src/adapters/database/uow.py` (add `messages` property + import)
- Test: `tests/unit/test_message_repository.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_message_repository.py
from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.models import (
    Message,
    MessageKind,
    MessageRecipientKind,
    MessageSenderKind,
)


def _uow(owner: str = "dev-user") -> SqlUnitOfWork:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return SqlUnitOfWork(make_session_factory(engine), required_filters={"owner_id": owner})


def _msg(**over) -> Message:
    base = dict(
        owner_id="dev-user",
        sender_kind=MessageSenderKind.AGENT,
        sender_agent_id="a-lead",
        recipient_kind=MessageRecipientKind.AGENT,
        recipient_agent_id="a-eng",
        kind=MessageKind.DISPATCH,
        body="go",
        run_id="r1",
    )
    base.update(over)
    return Message(**base)


def test_create_and_get_roundtrips_all_fields():
    uow = _uow()
    with uow.transaction():
        created = uow.messages.create(_msg(subject="brief"))
    with uow.transaction():
        got = uow.messages.get(created.id)
    assert got.subject == "brief"
    assert got.sender_agent_id == "a-lead"
    assert got.recipient_agent_id == "a-eng"
    assert got.kind == MessageKind.DISPATCH


def test_list_filters_by_recipient_mailbox():
    uow = _uow()
    with uow.transaction():
        uow.messages.create(_msg(recipient_agent_id="a-eng"))
        uow.messages.create(_msg(recipient_agent_id="a-qa"))
    with uow.transaction():
        eng = uow.messages.list(filters={"recipient_agent_id": "a-eng"})
    assert eng.total == 1
    assert eng.results[0].recipient_agent_id == "a-eng"


def test_owner_scoping_hides_other_tenants():
    uow = _uow(owner="dev-user")
    with uow.transaction():
        uow.messages.create(_msg(owner_id="dev-user"))
    other = SqlUnitOfWork(
        uow._session_factory, required_filters={"owner_id": "someone-else"}
    )
    with other.transaction():
        assert other.messages.list().total == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_message_repository.py -v`
Expected: FAIL — `AttributeError: 'SqlUnitOfWork' object has no attribute 'messages'`.

- [ ] **Step 3a: Add `MessageRow` to `src/adapters/database/orm.py`**

Add after `NotificationRow` (the imports `String`, `Text`, `DateTime`, `Mapped`, `mapped_column`, `datetime` are already present in this module):

```python
class MessageRow(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sender_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    sender_agent_id: Mapped[str | None] = mapped_column(String(32), index=True)
    recipient_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    recipient_agent_id: Mapped[str | None] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="chat")
    subject: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    run_id: Mapped[str | None] = mapped_column(String(32), index=True)
    work_item_id: Mapped[str | None] = mapped_column(String(32))
    project_id: Mapped[str | None] = mapped_column(String(32))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

Also add the assignee column to `WorkItemRow` (after the `status` column):

```python
    assignee_agent_id: Mapped[str | None] = mapped_column(String(32), index=True)
```

- [ ] **Step 3b: Add `MessageRepository` to `src/adapters/database/repositories.py`**

Add `MessageRow` to the `from adapters.database.orm import (...)` block and `Message` to the `from domain.models import (...)` block, then add the repository class (next to `NotificationRepository`):

```python
class MessageRepository(SqlRepository[Message]):
    orm_model = MessageRow
    dto = Message
```

- [ ] **Step 3c: Add `messages` to the `UnitOfWork` protocol in `src/adapters/database/ports.py`**

Add `Message` to the `from domain.models import (...)` block, then add to the protocol (next to `notifications`):

```python
    @property
    def messages(self) -> Repository[Message]: ...
```

- [ ] **Step 3d: Add the `messages` property to `src/adapters/database/uow.py`**

Add `MessageRepository` to the `from adapters.database.repositories import (...)` block, then add the property (next to `notifications`):

```python
    @property
    def messages(self) -> MessageRepository:
        return MessageRepository(self.session, self._required_filters)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_message_repository.py -v`
Expected: PASS (3 tests). The in-memory `Base.metadata.create_all` picks up `MessageRow` automatically.

- [ ] **Step 5: Commit**

```bash
git add src/adapters/database/orm.py src/adapters/database/repositories.py \
        src/adapters/database/ports.py src/adapters/database/uow.py \
        tests/unit/test_message_repository.py
git commit -m "feat: persist Message via owner-scoped MessageRepository"
```

---

## Task 4: Alembic migration (messages table + assignee column)

**Files:**
- Create: `migrations/versions/orch1msg01_messages_and_assignee.py`

The current head is `a6b2memory02` (verify with `uv run alembic heads`). The SQLite test path uses `Base.metadata.create_all`; Postgres uses this migration — it must match the ORM exactly.

- [ ] **Step 1: Write the migration**

```python
# migrations/versions/orch1msg01_messages_and_assignee.py
"""messages table and work_items.assignee_agent_id

Revision ID: orch1msg01
Revises: a6b2memory02
Create Date: 2026-06-14 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "orch1msg01"
down_revision: str | None = "a6b2memory02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("sender_kind", sa.String(length=10), nullable=False),
        sa.Column("sender_agent_id", sa.String(length=32), nullable=True),
        sa.Column("recipient_kind", sa.String(length=10), nullable=False),
        sa.Column("recipient_agent_id", sa.String(length=32), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=True),
        sa.Column("work_item_id", sa.String(length=32), nullable=True),
        sa.Column("project_id", sa.String(length=32), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_messages_owner_id", "messages", ["owner_id"])
    op.create_index("ix_messages_sender_agent_id", "messages", ["sender_agent_id"])
    op.create_index("ix_messages_recipient_agent_id", "messages", ["recipient_agent_id"])
    op.create_index("ix_messages_run_id", "messages", ["run_id"])
    op.add_column(
        "work_items",
        sa.Column("assignee_agent_id", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ix_work_items_assignee_agent_id", "work_items", ["assignee_agent_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_work_items_assignee_agent_id", table_name="work_items")
    op.drop_column("work_items", "assignee_agent_id")
    op.drop_index("ix_messages_run_id", table_name="messages")
    op.drop_index("ix_messages_recipient_agent_id", table_name="messages")
    op.drop_index("ix_messages_sender_agent_id", table_name="messages")
    op.drop_index("ix_messages_owner_id", table_name="messages")
    op.drop_table("messages")
```

- [ ] **Step 2: Verify the migration applies on a clean Postgres**

Run:
```bash
docker compose up -d --wait postgres
docker compose exec -T postgres psql -U yaah -d yaah -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
uv run alembic upgrade head
uv run alembic current
```
Expected: `alembic current` shows `orch1msg01 (head)`; no errors.

- [ ] **Step 3: Verify round-trip down/up**

Run: `uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: both succeed (drops then recreates the table/column cleanly).

- [ ] **Step 4: Run the full unit suite to confirm nothing regressed**

Run: `uv run pytest tests/unit -q`
Expected: PASS (including the existing `tests/unit/test_migrations.py` — the migration matches `MessageRow`/`WorkItemRow` exactly).

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/orch1msg01_messages_and_assignee.py
git commit -m "feat: migration for messages table and work_items.assignee_agent_id"
```

---

## Task 5: Gate check before PR

- [ ] **Step 1: Coverage gate**

Run: `make coverage`
Expected: PASS, ≥ 80%.

- [ ] **Step 2: Lint**

Run: `make lint`
Expected: clean.

- [ ] **Step 3: Push and open PR**

```bash
git push -u origin <branch>
gh pr create --base main --title "feat: messaging & assignee substrate" \
  --body "Adds the Message entity (agent mailbox + UI inbox row) and WorkItem.assignee_agent_id — the data substrate for lead-driven orchestration (ADR-0002, Plan 1 of 3). Model + ORM + owner-scoped repository + migration. No endpoints yet (deferred to consumers)."
```

---

## Self-Review

**Spec coverage (vs. `2026-06-14-lead-orchestration-design.md` §4):**
- `Message` model with all fields + agent-id validator → Task 1. ✓
- `WorkItem.assignee_agent_id` → Task 2. ✓
- Durable persistence + owner scoping + mailbox filter (`recipient_agent_id`) → Task 3. ✓
- `messages` table + assignee column migration → Task 4. ✓
- *Deferred by design:* new `RunEventType`s, `Dispatch`/`OrchestrationDecision`/`MonitorVerdict`, workflow/actors → Plans 2 & 3 (noted in Scope). HTTP endpoints → consumers.

**Placeholder scan:** none — every step has exact paths, real code, and concrete commands.

**Type consistency:** `Message`/`MessageKind`/`MessageSenderKind`/`MessageRecipientKind` names identical across Tasks 1 and 3; `MessageRepository.orm_model = MessageRow`, `dto = Message` matches the model/row; migration columns match `MessageRow` field-for-field (string lengths, nullability, `created_at` non-null).
