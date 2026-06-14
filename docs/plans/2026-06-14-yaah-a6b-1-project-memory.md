# A6b-1 Project Memory Loop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agents read project memory before working, and the LEARN curator emits a durable, reviewable memory diff (committed to `agent/memory-<run>`, persisted in Postgres) that survives workspace cleanup.

**Architecture:** Pure prompt change injects a memory pointer into PLAN/IMPLEMENT and strengthens the LEARN curator. A new `MemoryProposal` entity (model/orm/repo/uow/migration) stores the captured diff. Two new `GitPort` methods (`diff`, `commit_to_branch`) let a dedicated `capture_memory` Temporal activity — wired after LEARN, before cleanup — diff the memory paths, commit/push a memory branch, and persist the proposal. A read-only `GET /runs/{id}/memory` endpoint exposes it.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (sync), Alembic, Temporal, pytest. `uv run` for all commands. Fake git is the default in tests so existing suites stay green.

**Memory paths (the bounded set):** `CLAUDE.md`, `AGENTS.md`, `docs/adr` (prefix). Defined once in `src/domain/memory.py` and reused.

---

## File Structure

| File | Responsibility | Lane |
|---|---|---|
| `src/domain/prompts.py` (modify) | Memory pointer on PLAN/IMPLEMENT; stronger LEARN prompt | P |
| `src/domain/memory.py` (create) | `MEMORY_PATHS` constant + `changed_files(diff)` parser | W (shared) |
| `src/domain/models.py` (modify) | `MemoryProposalStatus`, `MemoryProposal` | M |
| `src/adapters/database/orm.py` (modify) | `MemoryProposalRow` | M |
| `src/adapters/database/repositories.py` (modify) | `MemoryProposalRepository` + imports | M |
| `src/adapters/database/uow.py` (modify) | `memory_proposals` property + import | M |
| `src/adapters/database/ports.py` (modify) | UoW protocol property + import | M |
| `migrations/versions/a6b1memory01_add_memory_proposals.py` (create) | `memory_proposals` table | M |
| `src/adapters/git/ports.py` (modify) | `diff`, `commit_to_branch` on `GitPort` | G |
| `src/adapters/git/local_git.py` (modify) | real-git impl | G |
| `src/adapters/git/fake.py` (modify) | in-memory impl | G |
| `src/interactors/temporal/activities.py` (modify) | `capture_memory` activity | W |
| `src/interactors/temporal/workflows.py` (modify) | call `capture_memory` after LEARN | W |
| `src/interactors/temporal/worker.py` (modify) | register `capture_memory` | W |
| `src/interactors/api/routes/runs.py` (modify) | `GET /runs/{id}/memory` | A |
| `src/interactors/api/routes/runs.py` (modify) | add `project_id` to `run_input` | W |

**Waves:** Wave 1 = lanes P, M, G (independent). Wave 2 = lane W (needs M + G + the shared `domain/memory.py`). Wave 3 = lane A (needs M).

> `domain/memory.py` is created in Wave 1 as the first task of lane W's dependencies. To keep lanes independent, **Task 4 (create `domain/memory.py`) belongs to Wave 1** and can run in any Wave-1 worktree; lane W (Wave 2) assumes it exists.

---

## LANE P — Prompts (Wave 1)

### Task 1: Memory pointer on PLAN and IMPLEMENT

**Files:**
- Modify: `src/domain/prompts.py`
- Test: `tests/unit/test_prompts.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_prompts.py`:

```python
from domain.prompts import for_stage
from domain.models import RunStage


def test_plan_prompt_points_to_project_memory():
    prompt, tools = for_stage(RunStage.PLAN, "Add login", ["works"])
    assert "CLAUDE.md" in prompt
    assert "AGENTS.md" in prompt
    assert "docs/adr" in prompt
    assert "Read" in tools


def test_implement_prompt_points_to_project_memory():
    prompt, _ = for_stage(RunStage.IMPLEMENT, "Add login", ["works"])
    assert "CLAUDE.md" in prompt
    assert "docs/adr" in prompt


def test_verify_prompt_has_no_memory_pointer():
    prompt, _ = for_stage(RunStage.VERIFY, "Add login", ["works"])
    assert "CLAUDE.md" not in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_prompts.py -k memory -v`
Expected: FAIL — `"CLAUDE.md" in prompt` assertion errors (pointer not present).

- [ ] **Step 3: Implement**

In `src/domain/prompts.py`, after the `_READ_TOOLS` line add the constant:

```python
_MEMORY_POINTER = (
    "Before you begin, read project memory if present: CLAUDE.md or AGENTS.md at the "
    "repo root, and any relevant files under docs/adr/. Honor the conventions, "
    "decisions, and gotchas recorded there.\n\n"
)
```

Change the PLAN and IMPLEMENT branches to prepend it:

```python
    if stage == RunStage.PLAN:
        return (_MEMORY_POINTER +
                f"Read the ticket and write an implementation plan to plan.md.\n\n"
                f"Ticket: {task_title}\n{body}\n\nAcceptance criteria:\n{ac}",
                ["Read", "Write"])
    if stage == RunStage.IMPLEMENT:
        return (_MEMORY_POINTER +
                "Implement this ticket by editing the repository in the working directory.\n\n"
                f"Ticket: {task_title}\n{body}\n\nAcceptance criteria:\n{ac}",
                list(_EDIT_TOOLS))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_prompts.py -v`
Expected: PASS (all, including any pre-existing prompt tests).

- [ ] **Step 5: Commit**

```bash
git add src/domain/prompts.py tests/unit/test_prompts.py
git commit -m "feat: inject project-memory pointer into PLAN and IMPLEMENT prompts"
```

### Task 2: Strengthen the LEARN curator prompt

**Files:**
- Modify: `src/domain/prompts.py`
- Test: `tests/unit/test_prompts.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_prompts.py`:

```python
def test_learn_prompt_requests_additions_and_deletions():
    prompt, tools = for_stage(RunStage.LEARN, "Add login", ["works"])
    lowered = prompt.lower()
    assert "additions" in lowered or "add" in lowered
    assert "deletion" in lowered or "remove" in lowered
    assert "CLAUDE.md" in prompt
    assert "docs/adr" in prompt
    assert "Edit" in tools  # editing existing memory files
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_prompts.py::test_learn_prompt_requests_additions_and_deletions -v`
Expected: FAIL — current LEARN prompt is "Summarise what changed…", no `docs/adr`, no `Edit` tool.

- [ ] **Step 3: Implement**

Replace the LEARN branch in `src/domain/prompts.py`:

```python
    if stage == RunStage.LEARN:
        return (
            "Update project memory with durable learnings from this run. Edit CLAUDE.md "
            "or AGENTS.md at the repo root (keep each concise, ~120 lines max) and add or "
            "update entries under docs/adr/ for architectural decisions. Propose additions "
            "AND deletions: remove stale or wrong guidance, record new conventions and "
            "gotchas. Only durable, project-wide knowledge belongs here.",
            ["Read", "Edit", "Write"],
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_prompts.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/domain/prompts.py tests/unit/test_prompts.py
git commit -m "feat: curator LEARN prompt updates project memory with adds and deletes"
```

---

## LANE M — Persistence (Wave 1)

### Task 3: `MemoryProposal` domain model

**Files:**
- Modify: `src/domain/models.py`
- Test: `tests/unit/test_memory_proposal_model.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_memory_proposal_model.py`:

```python
from domain.models import MemoryProposal, MemoryProposalStatus


def test_memory_proposal_defaults():
    p = MemoryProposal(owner_id="u", run_id="r", project_id="p", branch="agent/memory-r")
    assert len(p.id) == 32
    assert p.status == MemoryProposalStatus.PROPOSED
    assert p.diff == ""
    assert p.files == []
    assert p.created_at is not None


def test_memory_proposal_carries_diff_and_files():
    p = MemoryProposal(owner_id="u", run_id="r", project_id="p", branch="b",
                       diff="diff --git a/CLAUDE.md b/CLAUDE.md", files=["CLAUDE.md"])
    assert p.files == ["CLAUDE.md"]
    assert "CLAUDE.md" in p.diff
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_memory_proposal_model.py -v`
Expected: FAIL — `ImportError: cannot import name 'MemoryProposal'`.

- [ ] **Step 3: Implement**

In `src/domain/models.py`, add (near the other entity models, e.g. after `UsageRecord`):

```python
class MemoryProposalStatus(StrEnum):
    PROPOSED = "proposed"
    APPLIED = "applied"
    REJECTED = "rejected"


class MemoryProposal(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    run_id: str
    project_id: str
    branch: str
    diff: str = ""
    files: list[str] = Field(default_factory=list)
    status: MemoryProposalStatus = MemoryProposalStatus.PROPOSED
    created_at: datetime = Field(default_factory=utc_now)
```

(`StrEnum`, `BaseModel`, `Field`, `new_id`, `utc_now`, `datetime` are already imported at the top of `models.py`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_memory_proposal_model.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/domain/models.py tests/unit/test_memory_proposal_model.py
git commit -m "feat: add MemoryProposal domain model"
```

### Task 4: `domain/memory.py` — paths constant + diff parser (Wave 1, shared with lane W)

**Files:**
- Create: `src/domain/memory.py`
- Test: `tests/unit/test_memory.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_memory.py`:

```python
from domain.memory import MEMORY_PATHS, changed_files


def test_memory_paths_are_the_bounded_set():
    assert "CLAUDE.md" in MEMORY_PATHS
    assert "AGENTS.md" in MEMORY_PATHS
    assert "docs/adr" in MEMORY_PATHS


def test_changed_files_parses_unified_diff():
    diff = (
        "diff --git a/CLAUDE.md b/CLAUDE.md\n"
        "--- a/CLAUDE.md\n"
        "+++ b/CLAUDE.md\n"
        "@@ -1 +1,2 @@\n"
        " x\n+y\n"
        "diff --git a/docs/adr/0001.md b/docs/adr/0001.md\n"
        "--- /dev/null\n"
        "+++ b/docs/adr/0001.md\n"
        "@@ -0,0 +1 @@\n+new\n"
    )
    assert changed_files(diff) == ["CLAUDE.md", "docs/adr/0001.md"]


def test_changed_files_empty_for_empty_diff():
    assert changed_files("") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_memory.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'domain.memory'`.

- [ ] **Step 3: Implement**

Create `src/domain/memory.py`:

```python
"""Project-memory paths and diff helpers. Pure; no I/O."""

# The bounded set the harness captures and commits. Curator edits outside these
# paths are ignored (structural blast-radius guard).
MEMORY_PATHS: list[str] = ["CLAUDE.md", "AGENTS.md", "docs/adr"]

_NEW_FILE_MARKER = "+++ b/"


def changed_files(diff: str) -> list[str]:
    """Paths from the '+++ b/<path>' lines of a unified diff, in order."""
    files: list[str] = []
    for line in diff.splitlines():
        if line.startswith(_NEW_FILE_MARKER):
            files.append(line[len(_NEW_FILE_MARKER):])
    return files
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_memory.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/domain/memory.py tests/unit/test_memory.py
git commit -m "feat: add MEMORY_PATHS and changed_files diff parser"
```

### Task 5: `MemoryProposalRow` ORM + repository + UoW + ports

**Files:**
- Modify: `src/adapters/database/orm.py`
- Modify: `src/adapters/database/repositories.py`
- Modify: `src/adapters/database/uow.py`
- Modify: `src/adapters/database/ports.py`
- Test: `tests/unit/test_memory_proposal_repository.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_memory_proposal_repository.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.models import MemoryProposal


@pytest.fixture
def factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_memory_proposal_round_trips(factory):
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        created = uow.memory_proposals.create(MemoryProposal(
            owner_id="u1", run_id="r1", project_id="p1", branch="agent/memory-r1",
            diff="diff --git a/CLAUDE.md b/CLAUDE.md", files=["CLAUDE.md"]))
    with uow.transaction():
        fetched = uow.memory_proposals.get(created.id)
    assert fetched.run_id == "r1"
    assert fetched.files == ["CLAUDE.md"]
    assert fetched.status == "proposed"


def test_memory_proposal_is_owner_scoped(factory):
    SqlUnitOfWork(factory, required_filters={"owner_id": "owner"}).__class__  # noqa
    owner_uow = SqlUnitOfWork(factory, required_filters={"owner_id": "owner"})
    with owner_uow.transaction():
        p = owner_uow.memory_proposals.create(MemoryProposal(
            owner_id="owner", run_id="r1", project_id="p1", branch="b"))
    other_uow = SqlUnitOfWork(factory, required_filters={"owner_id": "intruder"})
    with other_uow.transaction():
        results = other_uow.memory_proposals.list(filters={"run_id": "r1"}).results
    assert results == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_memory_proposal_repository.py -v`
Expected: FAIL — `AttributeError: 'SqlUnitOfWork' object has no attribute 'memory_proposals'`.

- [ ] **Step 3: Implement (ORM row)**

In `src/adapters/database/orm.py`, add after `UsageRecordRow` (the last row class):

```python
class MemoryProposalRow(Base):
    __tablename__ = "memory_proposals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    branch: Mapped[str] = mapped_column(String(200), nullable=False)
    diff: Mapped[str] = mapped_column(Text, nullable=False, default="")
    files: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="proposed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

- [ ] **Step 4: Implement (repository)**

In `src/adapters/database/repositories.py`:
- add `MemoryProposalRow` to the `from adapters.database.orm import (...)` block (alphabetically after `McpServerRow`).
- add `MemoryProposal` to the `from domain.models import (...)` block.
- add the repository class (after `NotificationRepository`):

```python
class MemoryProposalRepository(SqlRepository[MemoryProposal]):
    orm_model = MemoryProposalRow
    dto = MemoryProposal
    default_order_by = "created_at"
```

- [ ] **Step 5: Implement (UoW + ports)**

In `src/adapters/database/uow.py`:
- add `MemoryProposalRepository` to the `from adapters.database.repositories import (...)` block.
- add the property (after `chat_messages`):

```python
    @property
    def memory_proposals(self) -> MemoryProposalRepository:
        return MemoryProposalRepository(self.session, self._required_filters)
```

In `src/adapters/database/ports.py`:
- add `MemoryProposal` to the `from domain.models import (...)` block.
- add the protocol property (after `chat_messages`):

```python
    @property
    def memory_proposals(self) -> Repository[MemoryProposal]: ...
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_memory_proposal_repository.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/adapters/database/orm.py src/adapters/database/repositories.py \
        src/adapters/database/uow.py src/adapters/database/ports.py \
        tests/unit/test_memory_proposal_repository.py
git commit -m "feat: persist MemoryProposal (orm, repository, uow, port)"
```

### Task 6: Alembic migration for `memory_proposals`

**Files:**
- Create: `migrations/versions/a6b1memory01_add_memory_proposals.py`
- Test: `tests/unit/test_migrations.py` (existing — the parity gate)

- [ ] **Step 1: Run the parity gate to verify it fails**

Run: `uv run pytest tests/unit/test_migrations.py -v`
Expected: FAIL — `Extra items in the right set: 'memory_proposals'` (ORM has the table, no migration creates it).

- [ ] **Step 2: Create the migration**

Create `migrations/versions/a6b1memory01_add_memory_proposals.py`:

```python
"""add memory_proposals

Revision ID: a6b1memory01
Revises: b196b5b90b23
Create Date: 2026-06-14 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a6b1memory01"
down_revision: str | None = "b196b5b90b23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memory_proposals",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("branch", sa.String(length=200), nullable=False),
        sa.Column("diff", sa.Text(), nullable=False),
        sa.Column("files", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_memory_proposals_owner_id"), "memory_proposals",
                    ["owner_id"], unique=False)
    op.create_index(op.f("ix_memory_proposals_run_id"), "memory_proposals",
                    ["run_id"], unique=False)
    op.create_index(op.f("ix_memory_proposals_project_id"), "memory_proposals",
                    ["project_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_memory_proposals_project_id"), table_name="memory_proposals")
    op.drop_index(op.f("ix_memory_proposals_run_id"), table_name="memory_proposals")
    op.drop_index(op.f("ix_memory_proposals_owner_id"), table_name="memory_proposals")
    op.drop_table("memory_proposals")
```

> If another migration has merged since this plan was written, set `down_revision` to the current head: run `uv run alembic heads` and use that id.

- [ ] **Step 3: Run the parity gate to verify it passes**

Run: `uv run pytest tests/unit/test_migrations.py -v`
Expected: PASS — migrated tables equal ORM metadata.

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/a6b1memory01_add_memory_proposals.py
git commit -m "feat: migration for memory_proposals table"
```

---

## LANE G — Git port (Wave 1)

### Task 7: `diff` + `commit_to_branch` on the fake (and protocol)

**Files:**
- Modify: `src/adapters/git/ports.py`
- Modify: `src/adapters/git/fake.py`
- Test: `tests/unit/test_fake_git.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_fake_git.py`:

```python
from adapters.git.fake import FakeGit


def test_fake_diff_returns_configured_memory_diff():
    git = FakeGit(memory_diff="diff --git a/CLAUDE.md b/CLAUDE.md")
    assert "CLAUDE.md" in git.diff("/ws", paths=["CLAUDE.md", "AGENTS.md", "docs/adr"])


def test_fake_diff_empty_by_default():
    git = FakeGit()
    assert git.diff("/ws", paths=["CLAUDE.md"]) == ""


def test_fake_commit_to_branch_records_when_memory_changed():
    git = FakeGit(memory_diff="diff --git a/CLAUDE.md b/CLAUDE.md")
    committed = git.commit_to_branch("/ws", branch="agent/memory-r1", base="main",
                                     paths=["CLAUDE.md"], message="memory")
    assert committed is True
    assert git.committed_to_branch == [
        ("/ws", "agent/memory-r1", "main", ("CLAUDE.md",), "memory")
    ]


def test_fake_commit_to_branch_noop_when_no_memory_changes():
    git = FakeGit()
    assert git.commit_to_branch("/ws", branch="b", base="main",
                                paths=["CLAUDE.md"], message="m") is False
    assert git.committed_to_branch == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_fake_git.py -k "diff or commit_to_branch" -v`
Expected: FAIL — `TypeError: FakeGit.__init__() got an unexpected keyword argument 'memory_diff'` / `AttributeError: 'FakeGit' object has no attribute 'diff'`.

- [ ] **Step 3: Implement (protocol)**

In `src/adapters/git/ports.py`, add to the `GitPort` protocol (after `current_branch`):

```python
    def diff(self, workspace_path: str, *, paths: list[str]) -> str: ...

    def commit_to_branch(
        self, workspace_path: str, *, branch: str, base: str,
        paths: list[str], message: str,
    ) -> bool: ...
```

- [ ] **Step 4: Implement (fake)**

In `src/adapters/git/fake.py`, update `__init__` and add the methods:

```python
    def __init__(self, has_changes: bool = True, memory_diff: str = ""):
        self._has_changes = has_changes
        self._memory_diff = memory_diff
        self.prepared: list[tuple] = []
        self.committed: list[tuple] = []
        self.pushed: list[tuple] = []
        self.committed_to_branch: list[tuple] = []
        self._branch = ""
```

```python
    def diff(self, workspace_path: str, *, paths: list[str]) -> str:
        return self._memory_diff

    def commit_to_branch(
        self, workspace_path: str, *, branch: str, base: str,
        paths: list[str], message: str,
    ) -> bool:
        if self._memory_diff:
            self.committed_to_branch.append(
                (workspace_path, branch, base, tuple(paths), message))
            return True
        return False
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_fake_git.py -v`
Expected: PASS (all, including pre-existing fake-git tests).

- [ ] **Step 6: Commit**

```bash
git add src/adapters/git/ports.py src/adapters/git/fake.py tests/unit/test_fake_git.py
git commit -m "feat: add diff and commit_to_branch to GitPort and FakeGit"
```

### Task 8: `diff` + `commit_to_branch` on `LocalGit` (real git)

**Files:**
- Modify: `src/adapters/git/local_git.py`
- Test: `tests/unit/test_local_git.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_local_git.py` (uses real `git` via tempdir; mirror existing tests' style):

```python
import subprocess
import tempfile
from pathlib import Path

from adapters.git.local_git import LocalGit


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True,
                   capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "--allow-empty", "-m", "init"], cwd=path, check=True,
                   capture_output=True)
    (path / "CLAUDE.md").write_text("# original\n")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-m", "add memory"], cwd=path, check=True,
                   capture_output=True)


def test_diff_shows_working_tree_memory_change():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        _init_repo(ws)
        (ws / "CLAUDE.md").write_text("# original\n# learned\n")
        out = LocalGit().diff(str(ws), paths=["CLAUDE.md", "AGENTS.md", "docs/adr"])
        assert "learned" in out
        assert "CLAUDE.md" in out


def test_commit_to_branch_commits_only_memory_paths():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        _init_repo(ws)
        (ws / "CLAUDE.md").write_text("# original\n# learned\n")
        (ws / "other.py").write_text("print('x')\n")  # non-memory change
        git = LocalGit()
        committed = git.commit_to_branch(str(ws), branch="agent/memory-r1", base="main",
                                         paths=["CLAUDE.md", "AGENTS.md", "docs/adr"],
                                         message="memory update")
        assert committed is True
        assert git.current_branch(str(ws)) == "agent/memory-r1"
        # the memory commit contains CLAUDE.md, not other.py
        files = subprocess.run(["git", "show", "--name-only", "--pretty=format:"],
                               cwd=ws, capture_output=True, text=True).stdout
        assert "CLAUDE.md" in files
        assert "other.py" not in files


def test_commit_to_branch_returns_false_with_no_memory_changes():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        _init_repo(ws)
        committed = LocalGit().commit_to_branch(str(ws), branch="b", base="main",
                                                paths=["CLAUDE.md"], message="m")
        assert committed is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_local_git.py -k "diff or commit_to_branch" -v`
Expected: FAIL — `AttributeError: 'LocalGit' object has no attribute 'diff'`.

- [ ] **Step 3: Implement**

In `src/adapters/git/local_git.py`, add to the `LocalGit` class (after `current_branch`):

```python
    def diff(self, workspace_path: str, *, paths: list[str]) -> str:
        return self._run(["diff", "--", *paths], cwd=workspace_path)

    def commit_to_branch(
        self, workspace_path: str, *, branch: str, base: str,
        paths: list[str], message: str,
    ) -> bool:
        # Create the memory branch off base, carrying the working-tree memory edits.
        self._run([*_AUTHOR, "checkout", "-b", branch, base], cwd=workspace_path)
        self._run(["add", "--", *paths], cwd=workspace_path)
        status = self._run(["status", "--porcelain", "--", *paths], cwd=workspace_path)
        if not status.strip():
            return False
        self._run([*_AUTHOR, "commit", "-m", message], cwd=workspace_path)
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_local_git.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/adapters/git/local_git.py tests/unit/test_local_git.py
git commit -m "feat: implement git diff and commit_to_branch on LocalGit"
```

---

## LANE W — capture_memory activity + workflow wiring (Wave 2)

> Depends on lanes M (MemoryProposal + uow), G (git methods), and Task 4 (`domain/memory.py`).

### Task 9: `capture_memory` activity

**Files:**
- Modify: `src/interactors/temporal/activities.py`
- Test: `tests/workflow/test_capture_memory.py`

- [ ] **Step 1: Write the failing test**

Create `tests/workflow/test_capture_memory.py`:

```python
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from adapters.git.fake import FakeGit
from adapters.storage.local import LocalStorageAdapter
from domain.models import Project, Run, WorkItem, WorkItemKind, WorkItemStatus
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


def _acts(factory, git, tmp):
    return RunActivities(factory, runtime=None,
                         storage=LocalStorageAdapter(base_dir=tmp),
                         git=git, forge=None)


def test_capture_memory_persists_proposal_and_event(factory):
    _seed(factory)
    with tempfile.TemporaryDirectory() as tmp:
        git = FakeGit(memory_diff="diff --git a/CLAUDE.md b/CLAUDE.md\n+++ b/CLAUDE.md\n+x\n")
        acts = _acts(factory, git, tmp)
        result = acts.capture_memory({"run_id": "r1", "owner_id": "dev-user",
                                      "project_id": "p1", "base": "main", "profile": "local"})
    assert result["proposal_id"] is not None
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        proposals = uow.memory_proposals.list(filters={"run_id": "r1"}).results
        events = uow.run_events.list(filters={"run_id": "r1"}).results
    assert len(proposals) == 1
    assert proposals[0].branch == "agent/memory-r1"
    assert proposals[0].files == ["CLAUDE.md"]
    assert git.committed_to_branch[0][1] == "agent/memory-r1"
    assert any("memory proposal" in e.message for e in events)


def test_capture_memory_noop_when_no_memory_changes(factory):
    _seed(factory)
    with tempfile.TemporaryDirectory() as tmp:
        git = FakeGit(memory_diff="")  # no memory edits
        acts = _acts(factory, git, tmp)
        result = acts.capture_memory({"run_id": "r1", "owner_id": "dev-user",
                                      "project_id": "p1", "base": "main", "profile": "local"})
    assert result["proposal_id"] is None
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        proposals = uow.memory_proposals.list(filters={"run_id": "r1"}).results
    assert proposals == []
    assert git.committed_to_branch == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/workflow/test_capture_memory.py -v`
Expected: FAIL — `AttributeError: 'RunActivities' object has no attribute 'capture_memory'`.

- [ ] **Step 3: Implement**

In `src/interactors/temporal/activities.py`, add the activity method to `RunActivities` (after `open_pr`):

```python
    @activity.defn(name="capture_memory")
    def capture_memory(self, payload: dict) -> dict:
        from domain.memory import MEMORY_PATHS, changed_files
        from domain.models import MemoryProposal
        run_id, owner_id = payload["run_id"], payload["owner_id"]
        workspace = self._storage.local_path(f"runs/{run_id}")
        diff = self._git.diff(workspace, paths=MEMORY_PATHS)
        if not diff.strip():
            self.record_event({"run_id": run_id, "owner_id": owner_id, "stage": "learn",
                               "type": RunEventType.AGENT_EVENT,
                               "message": "no memory changes"})
            return {"outcome": "ok", "proposal_id": None}
        branch = f"agent/memory-{run_id}"
        committed = self._git.commit_to_branch(
            workspace, branch=branch, base=payload["base"], paths=MEMORY_PATHS,
            message=f"chore: memory update for run {run_id}")
        if committed and payload["profile"] == "remote":
            try:
                token = self._forge.installation_token()
                self._git.push(workspace, branch, token=token)
            except Exception:  # noqa: BLE001 - push is best-effort; the proposal still persists
                pass
        files = changed_files(diff)
        uow = self._uow(owner_id)
        with uow.transaction():
            proposal = uow.memory_proposals.create(MemoryProposal(
                owner_id=owner_id, run_id=run_id, project_id=payload["project_id"],
                branch=branch, diff=diff, files=files))
        self.record_event({"run_id": run_id, "owner_id": owner_id, "stage": "learn",
                           "type": RunEventType.AGENT_EVENT,
                           "message": f"memory proposal: {len(files)} file(s) on {branch}"})
        return {"outcome": "ok", "proposal_id": proposal.id}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/workflow/test_capture_memory.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/interactors/temporal/activities.py tests/workflow/test_capture_memory.py
git commit -m "feat: capture_memory activity persists curator memory diff"
```

### Task 10: Wire `capture_memory` into the workflow + register on worker + pass project_id

**Files:**
- Modify: `src/interactors/temporal/workflows.py`
- Modify: `src/interactors/temporal/worker.py`
- Modify: `src/interactors/api/routes/runs.py` (add `project_id` to `run_input`)
- Test: `tests/workflow/test_run_workflow.py` (existing time-skipping workflow test — extend) OR `tests/workflow/test_capture_memory_workflow.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/workflow/test_capture_memory_workflow.py`. This asserts the workflow calls `capture_memory` on the happy path. Mirror the existing workflow test harness — inspect `tests/workflow/test_run_workflow.py` for the exact `WorkflowEnvironment` + worker fixture in this repo and reuse it. The behavioral assertion:

```python
# After a full FULL_AUTO run completes, a MemoryProposal exists for the run.
# (FakeGit configured with memory_diff so capture commits + persists.)
#
# Pattern (adapt to the repo's existing workflow-test fixture):
#   env = await WorkflowEnvironment.start_time_skipping()
#   git = FakeGit(memory_diff="diff --git a/CLAUDE.md b/CLAUDE.md\n+++ b/CLAUDE.md\n+x\n")
#   acts = RunActivities(factory, runtime=FakeRuntime(), storage=LocalStorageAdapter(tmp),
#                        git=git, forge=None)
#   worker = Worker(env.client, task_queue="tq", workflows=[RunWorkflow],
#                   activities=[... all acts including acts.capture_memory ...],
#                   activity_executor=ThreadPoolExecutor(max_workers=4))
#   run inp with autonomy="full_auto", profile="local", project_id="p1", base="main"
#   await env.client.execute_workflow(RunWorkflow.run, inp, id="r1", task_queue="tq")
#   assert a MemoryProposal row exists for run_id "r1"
```

Write the concrete test by copying the existing workflow test's setup verbatim and adding the `MemoryProposal` assertion + `acts.capture_memory` in the activities list + `project_id`/`base` in the input.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/workflow/test_capture_memory_workflow.py -v`
Expected: FAIL — workflow does not call `capture_memory`, so no proposal row exists (assertion fails). If `capture_memory` is not registered, Temporal raises an activity-not-registered error — also a valid red.

- [ ] **Step 3: Implement (workflow)**

In `src/interactors/temporal/workflows.py`, after the `while` loop ends and before the final DONE persist + cleanup:

```python
        # Curator memory edits were made during LEARN; capture them before teardown.
        await workflow.execute_activity(
            "capture_memory",
            {"run_id": run_id, "owner_id": owner_id,
             "project_id": inp["project_id"], "base": inp.get("base", "main"),
             "profile": inp["profile"]},
            start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)
        await self._persist(run_id, owner_id, status=RunStatus.DONE, stage=RunStage.LEARN)
        await self._cleanup(run_id, owner_id)
        return RunStatus.DONE
```

(The early-return paths — cancelled/rejected/blocked/verify-exhausted — already return before this point, so memory is captured only on successful completion.)

- [ ] **Step 4: Implement (worker registration)**

In `src/interactors/temporal/worker.py`, add `acts.capture_memory` to the returned activities list:

```python
    return [acts.persist_run_state, acts.record_event, acts.record_usage, acts.run_stage,
            acts.cleanup_workspace, acts.provision_workspace, acts.open_pr,
            acts.record_notification, acts.capture_memory]
```

- [ ] **Step 5: Implement (pass project_id from the API)**

In `src/interactors/api/routes/runs.py`, add `"project_id": project.id,` to the `run_input` dict in `start_run` (the workflow reads `inp["project_id"]`):

```python
        run_input = {
            "run_id": run.id,
            "owner_id": run.owner_id,
            "task_id": task_id,
            "project_id": project.id,
            "autonomy": project.autonomy,
            ...
        }
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/workflow/ -v`
Expected: PASS (new test + existing workflow tests still green).

- [ ] **Step 7: Commit**

```bash
git add src/interactors/temporal/workflows.py src/interactors/temporal/worker.py \
        src/interactors/api/routes/runs.py tests/workflow/test_capture_memory_workflow.py
git commit -m "feat: wire capture_memory after LEARN; pass project_id to the run"
```

---

## LANE A — Read endpoint (Wave 3)

> Depends on lane M (uow.memory_proposals).

### Task 11: `GET /runs/{run_id}/memory`

**Files:**
- Modify: `src/interactors/api/routes/runs.py`
- Test: `tests/integration/test_runs_api.py` (extend) or `tests/integration/test_run_memory_api.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_run_memory_api.py`. Reuse the existing TestClient + seeding helpers from `tests/integration/test_runs_api.py` (inspect that file for its `client`/seed fixtures and mirror them). Assertions:

```python
# Arrange: a run with a persisted MemoryProposal (write one via the app's session_factory
# using SqlUnitOfWork, same pattern test_runs_api.py uses to seed runs/work-items).
#
# Act + Assert (present):
#   resp = client.get(f"/runs/{run_id}/memory")
#   assert resp.status_code == 200
#   body = resp.json()
#   assert body["success"] is True
#   assert body["data"]["branch"] == "agent/memory-<run>"
#   assert body["data"]["files"] == ["CLAUDE.md"]
#
# Act + Assert (absent — run exists, no proposal):
#   resp = client.get(f"/runs/{other_run_id}/memory")
#   assert resp.status_code == 200
#   assert resp.json()["data"] is None
#
# Act + Assert (unknown run -> 404 enveloped):
#   resp = client.get("/runs/doesnotexist/memory")
#   assert resp.status_code == 404
#   assert resp.json()["success"] is False
```

Write the concrete test by copying `test_runs_api.py`'s fixtures and seeding a `MemoryProposal` through `SqlUnitOfWork`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_run_memory_api.py -v`
Expected: FAIL — route returns 404 for the memory path (endpoint not defined) on the "present" case.

- [ ] **Step 3: Implement**

In `src/interactors/api/routes/runs.py`, add after `list_run_audit`:

```python
@router.get("/runs/{run_id}/memory")
def get_run_memory(run_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        uow.runs.get(run_id)  # 404 if unknown / cross-tenant
        page = uow.memory_proposals.list(
            filters={"run_id": run_id}, order_by="-created_at", page_size=1)
    data = page.results[0].model_dump(mode="json") if page.results else None
    return ok(data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_run_memory_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/interactors/api/routes/runs.py tests/integration/test_run_memory_api.py
git commit -m "feat: GET /runs/{id}/memory returns the run's memory proposal"
```

---

## Final verification (after all lanes merge into the integration branch)

- [ ] **Full backend suite + lint:**

```bash
uv run ruff check src tests
uv run pytest -q
```
Expected: all green; coverage ≥ 80% (`make coverage`).

- [ ] **Migration parity holds:**

```bash
uv run pytest tests/unit/test_migrations.py -v
```
Expected: PASS (`memory_proposals` in both ORM + migrations).

---

## Self-Review

**Spec coverage:**
- §A memory injection → Task 1 (PLAN/IMPLEMENT pointer). ✔
- §B curator + diff capture → Task 2 (LEARN prompt) + Task 9 (diff capture). ✔
- §C durable artifact → Tasks 3, 5, 6. ✔
- §D git port additions → Tasks 7, 8. ✔
- §E workflow/activity wiring → Tasks 9, 10 (incl. push-and-hold, empty-diff no-op, project_id plumbing). ✔
- §F API + testing → Task 11; tests in every task. ✔
- Memory-paths constant → Task 4. ✔
- Out-of-scope items (role repo, review UI, auto-apply, progress.md, RAG) — none implemented. ✔

**Type consistency:** `MemoryProposal(owner_id, run_id, project_id, branch, diff, files, status, created_at)` is identical across model (T3), row (T5), repository DTO (T5), activity construction (T9), and endpoint dump (T11). `commit_to_branch(workspace_path, *, branch, base, paths, message) -> bool` and `diff(workspace_path, *, paths) -> str` are identical across protocol (T7), fake (T7), local_git (T8), and call site (T9). `capture_memory` payload keys (`run_id, owner_id, project_id, base, profile`) match the workflow call (T10). `MEMORY_PATHS` / `changed_files` defined in T4 and consumed in T9.

**Placeholder scan:** No TBD/TODO. Tasks 10 and 11 reference "copy the existing workflow/integration test fixture" rather than inlining a fixture this plan can't see verbatim — the behavioral assertions and all production code are fully specified; only the harness boilerplate is delegated to the existing sibling test, which is the correct DRY move.
