# Role Memory (A6b-3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give each agent role a durable, cross-project memory in the DB (append-only, full history), injected into the role's agent before its work (current project by default, all projects when the lead widens the dispatch), self-authored by the agent, plus a read API — while reviving the project-memory read pointer the orchestrator cutover left dormant.

**Architecture:** A new owner-scoped `role_memory_entries` table (DTO → ORM → repository → UoW → Alembic, mirroring `AuditEvent`). `agent_step` loads the role's recent entries (filtered by `project_id` unless the dispatch's `memory_scope == "all"`), injects a bounded digest + a memory pointer into the engineer brief, and after the agent runs persists `.orchestration/role-memory.md` as one entry. No git/file role memory — DB inserts are naturally parallel-safe.

**Tech Stack:** Python 3.12, `uv`, SQLAlchemy 2.0 + Postgres (SQLite in-memory for tests), Alembic, Pydantic v2, Temporal, FastAPI + httpx tests. Spec: `docs/specs/2026-06-16-role-memory-design.md`.

**Conventions (read before starting):**
- Tests: `uv run pytest <path> -q`. Gate: `make coverage` (80%) + `uv run ruff check src tests` (lines ≤100, no `;` multi-statement lines).
- Domain is pure (no I/O). Activities are the only DB writers. Immutable updates via `model_copy`. IDs are 32-char uuid-hex (`new_id`), timestamps `utc_now`. New entity stack follows `docs/architecture.md` → "Adding a new entity".
- Each phase = one PR off the latest `main`, in a git worktree. Commit per task.

---

## Phase 1 — Domain + persistence (PR 1)

A new append-only entity + a pure digest helper. Additive; no behavior change.

### Task 1.1: `RoleMemoryEntry` domain DTO

**Files:**
- Modify: `src/domain/models.py` (add the DTO near `AuditEvent`)
- Test: `tests/unit/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_models.py  (append)
def test_role_memory_entry_defaults_and_role():
    from domain.models import RoleMemoryEntry, AgentRole
    e = RoleMemoryEntry(owner_id="u1", role=AgentRole.BACKEND, content="prefer small PRs",
                        run_id="r1", project_id="p1")
    assert len(e.id) == 32 and e.role == AgentRole.BACKEND
    assert e.content == "prefer small PRs" and e.created_at is not None
    # role accepts the string form too (coerced to the enum)
    e2 = RoleMemoryEntry(owner_id="u1", role="qa", content="run the full suite")
    assert e2.role == AgentRole.QA and e2.run_id is None and e2.project_id is None
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/unit/test_models.py::test_role_memory_entry_defaults_and_role -q`
Expected: FAIL (`ImportError: cannot import name 'RoleMemoryEntry'`).

- [ ] **Step 3: Implement** (add after the `AuditEvent` class in `src/domain/models.py`; it already imports `new_id`, `utc_now`, `AgentRole`, `BaseModel`, `Field`, `datetime`):

```python
class RoleMemoryEntry(BaseModel):
    """One durable, append-only role-level learning. Owner-scoped; cross-project (project_id
    records origin but reads can span projects)."""

    id: str = Field(default_factory=new_id)
    owner_id: str
    role: AgentRole
    content: str
    run_id: str | None = None
    project_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
```

- [ ] **Step 4: Run** `uv run pytest tests/unit/test_models.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/domain/models.py tests/unit/test_models.py
git commit -m "feat: RoleMemoryEntry domain model"
```

### Task 1.2: ORM row + repository + UoW property + migration

**Files:**
- Modify: `src/adapters/database/orm.py` (new `RoleMemoryRow` near `AuditEventRow`)
- Modify: `src/adapters/database/repositories.py` (`RoleMemoryRepository`)
- Modify: `src/adapters/database/uow.py` (`role_memory` property)
- Create: `migrations/versions/rolemem01_role_memory_entries.py`
- Test: `tests/unit/test_role_memory_repository.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_role_memory_repository.py  (new file)
from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.models import AgentRole, RoleMemoryEntry


def _factory():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def test_role_memory_append_project_and_cross_project_queries():
    factory = _factory()
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        uow.role_memory.create(RoleMemoryEntry(owner_id="u1", role=AgentRole.BACKEND,
                                               content="p1 note", project_id="p1"))
        uow.role_memory.create(RoleMemoryEntry(owner_id="u1", role=AgentRole.BACKEND,
                                               content="p2 note", project_id="p2"))
        uow.role_memory.create(RoleMemoryEntry(owner_id="u1", role=AgentRole.QA,
                                               content="qa note", project_id="p1"))
    with uow.transaction():
        proj = uow.role_memory.list(filters={"role": "backend", "project_id": "p1"}).results
        allp = uow.role_memory.list(filters={"role": "backend"},
                                    order_by="-created_at").results
    assert {e.content for e in proj} == {"p1 note"}                 # project-scoped
    assert {e.content for e in allp} == {"p1 note", "p2 note"}      # cross-project


def test_role_memory_owner_isolation():
    factory = _factory()
    a = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    b = SqlUnitOfWork(factory, required_filters={"owner_id": "u2"})
    with a.transaction():
        a.role_memory.create(RoleMemoryEntry(owner_id="u1", role=AgentRole.BACKEND, content="x"))
    with b.transaction():
        assert b.role_memory.list(filters={"role": "backend"}).total == 0
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/unit/test_role_memory_repository.py -q`
Expected: FAIL (`AttributeError: 'SqlUnitOfWork' object has no attribute 'role_memory'`).

- [ ] **Step 3: ORM row** (add to `src/adapters/database/orm.py` near `AuditEventRow`; `String`, `Text`, `DateTime`, `Mapped`, `mapped_column`, `datetime` are already imported there):

```python
class RoleMemoryRow(Base):
    __tablename__ = "role_memory_entries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(32))
    project_id: Mapped[str | None] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

- [ ] **Step 4: Repository** (`src/adapters/database/repositories.py`): add `RoleMemoryRow` to the `from .orm import (...)` block and `RoleMemoryEntry` to the `from domain.models import (...)` block, then add the subclass next to `AuditEventRepository`:

```python
class RoleMemoryRepository(SqlRepository[RoleMemoryEntry]):
    orm_model = RoleMemoryRow
    dto = RoleMemoryEntry
```

- [ ] **Step 5: UoW property** (`src/adapters/database/uow.py`): add `RoleMemoryRepository` to the `from .repositories import (...)` block, then add the property next to `audit_events`:

```python
    @property
    def role_memory(self) -> RoleMemoryRepository:
        return RoleMemoryRepository(self.session, self._required_filters)
```

- [ ] **Step 6: Migration** (`migrations/versions/rolemem01_role_memory_entries.py`):

```python
"""role_memory_entries

Revision ID: rolemem01
Revises: orch1msg01
Create Date: 2026-06-16 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "rolemem01"
down_revision: str | None = "orch1msg01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "role_memory_entries",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=True),
        sa.Column("project_id", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_role_memory_entries_owner_id"), "role_memory_entries", ["owner_id"])
    op.create_index(op.f("ix_role_memory_entries_role"), "role_memory_entries", ["role"])
    op.create_index(
        op.f("ix_role_memory_entries_project_id"), "role_memory_entries", ["project_id"])


def downgrade() -> None:
    op.drop_table("role_memory_entries")
```

- [ ] **Step 7: Run tests + confirm migration chains**

Run: `uv run pytest tests/unit/test_role_memory_repository.py tests/unit -q` → PASS.
Run: `uv run alembic heads` → expect a single head `rolemem01`.

- [ ] **Step 8: Commit**

```bash
git add src/adapters/database tests/unit/test_role_memory_repository.py migrations/versions/rolemem01_role_memory_entries.py
git commit -m "feat: role_memory_entries table + repository + migration"
```

### Task 1.3: `role_memory_digest` pure helper

**Files:**
- Modify: `src/domain/memory.py`
- Test: `tests/unit/test_memory.py` (the file that tests `domain/memory`; if absent, create `tests/unit/test_role_memory_digest.py`)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_memory.py  (append; or new tests/unit/test_role_memory_digest.py)
def test_role_memory_digest_bounds_and_order():
    from domain.memory import role_memory_digest
    from domain.models import AgentRole, RoleMemoryEntry
    # caller passes newest-first; digest preserves order, caps count
    entries = [RoleMemoryEntry(owner_id="u1", role=AgentRole.BACKEND, content=f"note {i}")
               for i in range(5)]
    out = role_memory_digest(entries, max_entries=3, max_chars=10_000)
    assert out == "- note 0\n- note 1\n- note 2"
    # char budget stops early
    big = [RoleMemoryEntry(owner_id="u1", role=AgentRole.BACKEND, content="x" * 50)
           for _ in range(5)]
    capped = role_memory_digest(big, max_entries=5, max_chars=60)
    assert capped.count("\n") == 0  # only the first entry fits
    assert role_memory_digest([], max_entries=3, max_chars=100) == ""
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/unit/test_memory.py -k role_memory_digest -q`
Expected: FAIL (`ImportError`/`AttributeError` for `role_memory_digest`).

- [ ] **Step 3: Implement** (append to `src/domain/memory.py`):

```python
def role_memory_digest(entries, *, max_entries: int, max_chars: int) -> str:
    """Render up to `max_entries` role-memory entries (caller-ordered, newest first) into a
    bounded markdown list, stopping before exceeding `max_chars`. Pure."""
    lines: list[str] = []
    used = 0
    for entry in entries[:max_entries]:
        block = f"- {entry.content.strip()}"
        if lines and used + len(block) + 1 > max_chars:
            break
        if not lines and len(block) > max_chars:
            break
        used += len(block) + (1 if lines else 0)
        lines.append(block)
    return "\n".join(lines)
```

- [ ] **Step 4: Run** `uv run pytest tests/unit/test_memory.py -q` → PASS.

- [ ] **Step 5: Commit + open PR 1**

```bash
git add src/domain/memory.py tests/unit/test_memory.py
git commit -m "feat: role_memory_digest bounded renderer"
make coverage && uv run ruff check src tests
git push -u origin feat/role-memory-1
gh pr create --title "feat: role memory phase 1 — DB entity + digest" --body "Phase 1 of role memory (spec docs/specs/2026-06-16-role-memory-design.md): role_memory_entries table (DTO/ORM/repository/UoW/migration) + role_memory_digest. Additive, no behavior change."
```

---

## Phase 2 — Wire read + write + `memory_scope` (PR 2)

Make role memory live: the lead can widen scope, `agent_step` injects the digest + revives project read, and persists the agent's authored learnings.

### Task 2.1: `Dispatch.memory_scope`

**Files:**
- Modify: `src/domain/orchestration/core.py` (`Dispatch`)
- Test: `tests/unit/test_orchestration.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_orchestration.py  (append)
def test_dispatch_memory_scope_default_and_validation():
    from domain.orchestration import Dispatch, parse_decision, OrchestrationContractError
    import pytest
    d = Dispatch(target_role="backend", instructions="x")
    assert d.memory_scope == "project"
    d2 = Dispatch(target_role="backend", instructions="x", memory_scope="all")
    assert d2.memory_scope == "all"
    # invalid value rejected through the lead-decision parse contract
    raw = {"intent": "continue",
           "dispatches": [{"target_role": "backend", "instructions": "x",
                           "memory_scope": "everything"}]}
    with pytest.raises(OrchestrationContractError):
        parse_decision(raw)
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/unit/test_orchestration.py::test_dispatch_memory_scope_default_and_validation -q`
Expected: FAIL (`Dispatch` has no `memory_scope`; the invalid case does not raise).

- [ ] **Step 3: Implement** — add the field to `Dispatch` in `src/domain/orchestration/core.py` (the module already imports `Field`; add `Literal` to the `typing` import or `from typing import Literal`):

```python
class Dispatch(BaseModel):
    """The lead's 'trigger an agent' unit."""

    target_role: AgentRole
    instructions: str
    acceptance: list[str] = Field(default_factory=list)
    memory_scope: Literal["project", "all"] = "project"
```

(`parse_decision` validates `OrchestrationDecision`, which contains `Dispatch`, so the invalid value raises `ValidationError` → `OrchestrationContractError` with no extra code.)

- [ ] **Step 4: Run** `uv run pytest tests/unit/test_orchestration.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/domain/orchestration/core.py tests/unit/test_orchestration.py
git commit -m "feat: Dispatch.memory_scope (project|all) for lead-widened role memory"
```

### Task 2.2: `memory_pointer` prompt helper + lead-prompt line

**Files:**
- Modify: `src/domain/agent/prompts.py` (`memory_pointer`)
- Modify: `src/domain/orchestration/prompts.py` (`build_orchestrator_prompt` — document `memory_scope`)
- Test: `tests/unit/test_prompts.py` (tests `domain/agent/prompts`), `tests/unit/test_orchestration_prompts.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_prompts.py  (append)
def test_memory_pointer_with_and_without_role():
    from domain.agent.prompts import memory_pointer
    from domain.models import AgentRole
    p = memory_pointer(AgentRole.BACKEND, role_digest="- prefer small PRs")
    assert "CLAUDE.md" in p and "docs/adr" in p           # revives project read
    assert "backend" in p and "prefer small PRs" in p     # role digest injected
    assert ".orchestration/role-memory.md" in p           # self-authoring instruction
    none = memory_pointer(None, role_digest="")
    assert "CLAUDE.md" in none and "role-memory.md" not in none  # project pointer only

# tests/unit/test_orchestration_prompts.py  (append)
def test_orchestrator_prompt_documents_memory_scope():
    from domain.orchestration import OrchestrationState, build_orchestrator_prompt
    from domain.models import AgentRole
    p = build_orchestrator_prompt(task_title="T", acceptance_criteria=[], body="",
                                  state=OrchestrationState(), available_roles=[AgentRole.BACKEND])
    assert "memory_scope" in p
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/unit/test_prompts.py::test_memory_pointer_with_and_without_role tests/unit/test_orchestration_prompts.py::test_orchestrator_prompt_documents_memory_scope -q`
Expected: FAIL (`memory_pointer` undefined; prompt lacks `memory_scope`).

- [ ] **Step 3: Implement `memory_pointer`** (add to `src/domain/agent/prompts.py`):

```python
def memory_pointer(role, role_digest: str = "") -> str:
    """Prepended to an orchestrator agent's brief: revives the project-memory read pointer and
    (when role is known) injects the role digest + a self-authoring instruction."""
    base = (
        "Before you begin, read project memory if present: CLAUDE.md or AGENTS.md at the repo "
        "root, and relevant files under docs/adr/. Honor the conventions and gotchas there."
    )
    if role is None:
        return base + "\n\n"
    name = role.value if hasattr(role, "value") else str(role)
    digest = role_digest.strip() or "(none yet)"
    return (
        f"{base}\n\nYour accumulated {name} memory from past work:\n{digest}\n\n"
        f"If you learn something durable about working as {name}, append a concise note (one or "
        "two lines) to .orchestration/role-memory.md — only durable role-level knowledge, not "
        "task specifics.\n\n"
    )
```

- [ ] **Step 4: Implement the lead-prompt line** — in `build_orchestrator_prompt` (`src/domain/orchestration/prompts.py`), extend the decision-fields sentence to mention the field. Find the string that lists decision JSON fields ("...assignee_role (the role primarily responsible); rationale...") and add:

```python
        "dispatches may set memory_scope ('project' default, or 'all' to draw on that role's "
        "memory from every project for a large or cross-cutting task). "
```
(insert it into the existing fields description string so it appears in the prompt).

- [ ] **Step 5: Run** the two test files → PASS.

- [ ] **Step 6: Commit**

```bash
git add src/domain/agent/prompts.py src/domain/orchestration/prompts.py tests/unit/test_prompts.py tests/unit/test_orchestration_prompts.py
git commit -m "feat: memory_pointer (revive project read + role digest) + lead memory_scope prompt"
```

### Task 2.3: Inject + persist in `agent_step`; thread `project_id`/`memory_scope`

**Files:**
- Modify: `src/interactors/temporal/activities.py` (`agent_step`)
- Modify: `src/interactors/temporal/workflows.py` (`AgentWorkflow.run`'s `agent_step` payload; `OrchestratorWorkflow` dispatch passes `memory_scope`)
- Test: `tests/unit/test_orchestration_activities.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_orchestration_activities.py  (append; reuse _factory/_seed_run/_acts/_ResultSpy)
def test_agent_step_injects_role_digest_project_default_and_all(tmp_path):
    from adapters.database.uow import SqlUnitOfWork
    from adapters.storage.local import LocalStorageAdapter
    from domain.models import AgentRole, RoleMemoryEntry
    factory = _factory()
    _seed_run(factory)  # seeds run r1 with project_id p1 (owner dev-user)
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        uow.role_memory.create(RoleMemoryEntry(owner_id="dev-user", role=AgentRole.BACKEND,
                                               content="this-project note", project_id="p1"))
        uow.role_memory.create(RoleMemoryEntry(owner_id="dev-user", role=AgentRole.BACKEND,
                                               content="other-project note", project_id="p2"))
    spy = _ResultSpy()
    acts = _acts(factory, runtime=spy, storage=LocalStorageAdapter(base_dir=str(tmp_path)))
    # default scope -> only this project's note
    acts.agent_step({"run_id": "r1", "owner_id": "dev-user", "role": "backend", "incoming": "do",
                     "task_title": "T", "acceptance_criteria": [], "team_id": None,
                     "project_id": "p1"})
    assert "this-project note" in spy.ctx.instructions
    assert "other-project note" not in spy.ctx.instructions
    assert "CLAUDE.md" in spy.ctx.instructions  # project read revived
    # memory_scope=all -> both projects
    acts.agent_step({"run_id": "r1", "owner_id": "dev-user", "role": "backend", "incoming": "do",
                     "task_title": "T", "acceptance_criteria": [], "team_id": None,
                     "project_id": "p1", "memory_scope": "all"})
    assert "other-project note" in spy.ctx.instructions


def test_agent_step_persists_authored_role_memory(tmp_path):
    from adapters.database.uow import SqlUnitOfWork
    from adapters.storage.local import LocalStorageAdapter
    factory = _factory()
    _seed_run(factory)
    storage = LocalStorageAdapter(base_dir=str(tmp_path))

    class _Author:
        def run_stage(self, ctx):
            from domain.agent import AgentEvent, StageResult
            storage.write_bytes("runs/r1/.orchestration/role-memory.md",
                                b"Keep migrations reversible.")
            yield AgentEvent(type="result", stage=ctx.stage,
                             data=StageResult(outcome="ok").model_dump())
        def cancel(self, run_id): ...

    acts = _acts(factory, runtime=_Author(), storage=storage)
    acts.agent_step({"run_id": "r1", "owner_id": "dev-user", "role": "backend", "incoming": "do",
                     "task_title": "T", "acceptance_criteria": [], "team_id": None,
                     "project_id": "p1"})
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        rows = uow.role_memory.list(filters={"role": "backend"}).results
    assert len(rows) == 1
    assert rows[0].content == "Keep migrations reversible."
    assert rows[0].project_id == "p1" and rows[0].run_id == "r1"
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/unit/test_orchestration_activities.py -k "role_digest or authored_role_memory" -q`
Expected: FAIL (no injection; no persisted entry).

- [ ] **Step 3: Implement in `agent_step`** (`src/interactors/temporal/activities.py`). At the top of `agent_step`, after `role = AgentRole(payload["role"]) if payload.get("role") else None`, build the pointer and prepend it; after `_run_instructed_agent` returns, persist the artifact.

Add the imports at the top of the method (or module): `from domain.agent.prompts import memory_pointer`, `from domain.memory import role_memory_digest`, `from domain.models import RoleMemoryEntry`.

Replace the `instructions = (...)` assignment with:

```python
        digest = ""
        if role is not None:
            filters = {"role": role.value}
            if payload.get("memory_scope") != "all" and payload.get("project_id"):
                filters["project_id"] = payload["project_id"]
            uow = self._uow(owner_id)
            with uow.transaction():
                entries = uow.role_memory.list(
                    filters=filters, order_by="-created_at", page_size=20).results
            digest = role_memory_digest(entries, max_entries=15, max_chars=2000)
        instructions = (
            memory_pointer(role, digest)
            + f"{payload.get('incoming', '')}\n\nIf you need to message a teammate or the "
            "user, write a JSON list of outbound messages to .orchestration/outbox.json."
        )
```

After `result = self._run_instructed_agent(...)` and the `outcome = AgentOutcome(result.outcome)` line, add persistence (read from the agent's actual workspace — it may be an engineer instance worktree):

```python
        workspace_key = payload.get("workspace_key") or f"runs/{run_id}"
        learned = self._storage.read_text(f"{workspace_key}/.orchestration/role-memory.md")
        if role is not None and learned and learned.strip():
            try:
                uow = self._uow(owner_id)
                with uow.transaction():
                    uow.role_memory.create(RoleMemoryEntry(
                        owner_id=owner_id, role=role, content=learned.strip(),
                        run_id=run_id, project_id=payload.get("project_id")))
            except Exception:  # noqa: BLE001 - role memory is advisory; never fail the stage
                pass
```

(Note: the artifact is read via `workspace_key`, NOT `_read_artifact(run_id, ...)` which always reads the main `runs/{run_id}` workspace — engineers run in instance worktrees.)

- [ ] **Step 4: Thread `project_id` + `memory_scope` through the workflow** (`src/interactors/temporal/workflows.py`):

In `AgentWorkflow.run`'s `agent_step` payload, add `project_id` and `memory_scope` (the actor input already carries `project_id`; `memory_scope` is added in the next edit):

```python
                    {"run_id": run_id, "owner_id": owner_id, "role": role,
                     "incoming": msg.get("body", ""), "task_title": inp["task_title"],
                     "acceptance_criteria": inp.get("acceptance_criteria", []),
                     "team_id": inp.get("team_id"), "workspace_key": inp.get("workspace_key"),
                     "project_id": inp.get("project_id"),
                     "memory_scope": inp.get("memory_scope", "project")},
```

In `OrchestratorWorkflow`'s dispatch loop, pass the dispatch's `memory_scope` into the child `AgentWorkflow` input (add to the dict that starts `{"run_id": run_id, "owner_id": owner_id, "role": role,` ... within the `for i, d in enumerate(dispatches)` loop):

```python
                     "memory_scope": d.get("memory_scope", "project"),
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/unit/test_orchestration_activities.py tests/workflow/ -q`
Expected: PASS (existing orchestrator/agent workflow tests still green — the new payload keys are optional with defaults).

- [ ] **Step 6: Commit + open PR 2**

```bash
git add src/interactors/temporal tests/unit/test_orchestration_activities.py
git commit -m "feat: agent_step injects role digest + revives project read + persists authored role memory"
make coverage && uv run ruff check src tests
git push -u origin feat/role-memory-2
gh pr create --title "feat: role memory phase 2 — read/write wiring + memory_scope" --body "Phase 2: agent_step injects the role digest (project-default, lead-widened via Dispatch.memory_scope=all) and revives the dormant project-memory read; persists .orchestration/role-memory.md as an entry. Spec docs/specs/2026-06-16-role-memory-design.md."
```

---

## Phase 3 — Read API (PR 3)

### Task 3.1: `GET /role-memory`

**Files:**
- Create: `src/interactors/api/routes/role_memory.py`
- Modify: `src/interactors/api/app.py` (register the router)
- Test: `tests/integration/test_role_memory_api.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_role_memory_api.py  (new)
from fastapi.testclient import TestClient

from adapters.database.uow import SqlUnitOfWork
from domain.models import AgentRole, RoleMemoryEntry
from interactors.api.app import create_app
from interactors.api.settings import Settings


def _client():
    app = create_app(Settings(_env_file=None, database_url="sqlite:///:memory:"))
    return app, TestClient(app)


def test_list_role_memory_owner_scoped_newest_first():
    app, c = _client()
    factory = app.state.session_factory
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        uow.role_memory.create(RoleMemoryEntry(owner_id="dev-user", role=AgentRole.BACKEND,
                                               content="older", project_id="p1"))
        uow.role_memory.create(RoleMemoryEntry(owner_id="dev-user", role=AgentRole.BACKEND,
                                               content="newer", project_id="p2"))
        uow.role_memory.create(RoleMemoryEntry(owner_id="dev-user", role=AgentRole.QA,
                                               content="qa", project_id="p1"))
    resp = c.get("/role-memory?role=backend")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [e["content"] for e in data] == ["newer", "older"]  # newest first, qa excluded
    assert resp.json()["meta"]["total"] == 2
```

(`app.state.session_factory` is set by the app factory — `src/interactors/api/app.py:30`.)

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/integration/test_role_memory_api.py -q`
Expected: FAIL (404 — route not registered).

- [ ] **Step 3: Implement the route** (`src/interactors/api/routes/role_memory.py`):

```python
from fastapi import APIRouter, Depends, HTTPException, Query

from adapters.database.ports import UnitOfWork
from domain.models import AgentRole
from interactors.api.deps import get_uow
from interactors.api.envelope import ok

router = APIRouter(tags=["role-memory"])

_ROLES = {r.value for r in AgentRole}


@router.get("/role-memory")
def list_role_memory(
    role: str = Query(...),
    project_id: str | None = Query(default=None),
    page_size: int = Query(50, ge=1, le=200),
    page_number: int = Query(1, ge=1),
    uow: UnitOfWork = Depends(get_uow),
) -> dict:
    if role not in _ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of {_ROLES}")
    filters: dict = {"role": role}
    if project_id:
        filters["project_id"] = project_id
    with uow.transaction():
        page = uow.role_memory.list(
            filters=filters, order_by="-created_at",
            page_size=page_size, page_number=page_number,
        )
    return ok(
        [e.model_dump(mode="json") for e in page.results],
        meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number},
    )
```

- [ ] **Step 4: Register the router** (`src/interactors/api/app.py`): add `role_memory` to the `from interactors.api.routes import (...)` block (around line 63), and add `app.include_router(role_memory.router)` next to `app.include_router(audit.router)` (around line 90).

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/integration/test_role_memory_api.py tests/integration -q`
Expected: PASS.

- [ ] **Step 6: Commit + open PR 3**

```bash
git add src/interactors/api/routes/role_memory.py src/interactors/api/app.py tests/integration/test_role_memory_api.py
git commit -m "feat: GET /role-memory (owner-scoped history, newest-first)"
make coverage && uv run ruff check src tests
git push -u origin feat/role-memory-3
gh pr create --title "feat: role memory phase 3 — read API" --body "Phase 3: GET /role-memory?role=&project_id= owner-scoped, paginated, newest-first. Completes spec docs/specs/2026-06-16-role-memory-design.md."
```

---

## Final validation (after Phase 3)

- [ ] `make coverage` ≥ 80% and `uv run ruff check src tests` clean on each PR.
- [ ] `alembic upgrade head` applies `rolemem01` cleanly on Postgres (`make migrate`).
- [ ] Unit/integration: project-default vs `memory_scope=all` injection; authored artifact persisted with `project_id`/`run_id`; cross-project + owner-scoped repository queries; `GET /role-memory` newest-first owner-scoped.
- [ ] (Optional) real Claude run on a ticket, then a second run, confirming the second run's engineer brief carries the first run's authored role note (and a `memory_scope=all` dispatch pulls cross-project entries) — mirrors the parallel-engineers validation runbook.

## Notes / deferred (from the spec)

- Human review/approval gate before retention, automatic summarization/de-dup of accumulated entries, a delete/prune endpoint, and a board-UI surface for browsing a role's memory.
- The `for_stage(LEARN)` project-memory *curation* prompt remains unused (the orchestrator has no LEARN agent); only project-memory *reading* is revived here.
