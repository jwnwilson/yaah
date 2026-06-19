# Chat-driven commit → auto-run — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user converse with the team-lead refinement chat to draft epics/features/tasks, then with a natural-language "go" have the chat promote those drafts to `Ready`, activate their parents, and auto-start runs through the existing scheduler/orchestrator.

**Architecture:** Add one field to the refinement agent contract (`action: discuss|commit`) and one provenance column (`chat_session_id` on `WorkItem`). When the agent returns `action=commit`, the chat endpoint promotes the session's `DRAFT` tasks to `READY`, activates their parent epics/features, and reuses `reconcile_project` + `OrchestratorWorkflow` to launch runs — exactly the path the `activate` endpoint already uses. No new run-start machinery.

**Tech Stack:** Python 3.12 · FastAPI · SQLAlchemy 2.0 · Alembic · pytest · httpx.

**Spec:** `docs/plans/2026-06-19-yaah-chat-commit-autorun-design.md`

---

## Preconditions & conventions

- **Worktree (yaah rule — never commit to `main`):** before starting, create an isolated worktree off latest `main`:
  ```bash
  git worktree add -b feat/chat-commit-autorun ../yaah-chat-commit origin/main
  ```
  Do all work there. Move the design doc + this plan into the worktree if they were written in the primary checkout, so they ship in the same PR.
- TDD throughout; backend tests: `uv run pytest <path> -v`. Run `rm -rf ui/dist` before the full backend suite (stale build artifacts break collection).
- Commit per task with `<type>: <description>`.
- The Anthropic refinement adapter needs **no code change**: its tool schema is `RefinementOutput.model_json_schema()` and it parses via `RefinementOutput(**input)`, so the new `action` field flows through automatically. Task 5 adds a lock-in test only.

---

## Task 1: Refinement contract — `action` field + `select_committable`

**Files:**
- Modify: `src/domain/refinement.py`
- Test: `tests/unit/test_refinement.py`

- [ ] **Step 1: Write the failing test** — append to `tests/unit/test_refinement.py`:

```python
def test_output_action_defaults_to_discuss():
    from domain.refinement import RefinementAction, RefinementOutput

    out = RefinementOutput(reply="hi")
    assert out.action == RefinementAction.DISCUSS


def test_output_parses_commit_action():
    from domain.refinement import RefinementAction, RefinementOutput

    out = RefinementOutput(**{"reply": "starting", "action": "commit"})
    assert out.action == RefinementAction.COMMIT


def test_select_committable_picks_draft_tasks_and_their_parents():
    from domain.projects import WorkItem, WorkItemKind, WorkItemStatus
    from domain.refinement import select_committable

    epic = WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.EPIC, title="E")
    feat = WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.FEATURE,
                    parent_id=epic.id, title="F")
    ready_task = WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.TASK,
                          parent_id=feat.id, title="done", status=WorkItemStatus.READY)
    draft_task = WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.TASK,
                          parent_id=feat.id, title="todo", status=WorkItemStatus.DRAFT)

    plan = select_committable([epic, feat, ready_task, draft_task])

    assert plan.task_ids == [draft_task.id]          # only the DRAFT task
    assert plan.parent_ids == [feat.id]              # its direct parent, deduped
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_refinement.py -k "action or committable" -v`
Expected: FAIL with `ImportError` (no `RefinementAction` / `select_committable`).

- [ ] **Step 3: Write minimal implementation** — in `src/domain/refinement.py`:

Add `RefinementAction` near the top (after the imports, before `ChatRole`):

```python
class RefinementAction(StrEnum):
    DISCUSS = "discuss"
    COMMIT = "commit"
```

Add `action` to `RefinementOutput`:

```python
class RefinementOutput(BaseModel):
    reply: str = ""
    proposals: list[WorkItemProposal] = []
    epic_update: EpicSpecEdit | None = None
    updates: list[WorkItemEdit] = []
    action: RefinementAction = RefinementAction.DISCUSS
```

Add the pure commit-selection helper at the end of the file:

```python
class CommitPlan(BaseModel):
    """What a `commit` turn should start: the DRAFT tasks to mark READY and the direct
    parent ids to activate so the scheduler can see them. Pure — no I/O."""

    task_ids: list[str] = []
    parent_ids: list[str] = []


def select_committable(items: list[WorkItem]) -> CommitPlan:
    """Given a chat session's work items, pick the DRAFT tasks to promote and the distinct
    direct-parent ids that must be activated. Non-DRAFT items are ignored (idempotent)."""
    drafts = [
        i for i in items
        if i.kind == WorkItemKind.TASK and i.status == WorkItemStatus.DRAFT
    ]
    parent_ids: list[str] = []
    for t in drafts:
        if t.parent_id and t.parent_id not in parent_ids:
            parent_ids.append(t.parent_id)
    return CommitPlan(task_ids=[t.id for t in drafts], parent_ids=parent_ids)
```

Update the import line so `WorkItemStatus` is available:

```python
from domain.projects import WorkItem, WorkItemKind, WorkItemStatus
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_refinement.py -v`
Expected: PASS (all, including existing tests).

- [ ] **Step 5: Commit**

```bash
git add src/domain/refinement.py tests/unit/test_refinement.py
git commit -m "feat: RefinementOutput.action + select_committable commit policy"
```

---

## Task 2: Confirm-before-commit prompt

**Files:**
- Modify: `src/domain/refinement.py` (`system_prompt`)
- Test: `tests/unit/test_refinement.py`

- [ ] **Step 1: Write the failing test** — append:

```python
def test_system_prompt_explains_confirm_then_commit():
    from domain.refinement import system_prompt

    p = system_prompt("Alpha").lower()
    assert "confirm" in p and "commit" in p
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_refinement.py::test_system_prompt_explains_confirm_then_commit -v`
Expected: FAIL (assert; current prompt has neither word).

- [ ] **Step 3: Write minimal implementation** — extend the returned string in `system_prompt` (append one sentence before the closing paren):

```python
def system_prompt(project_name: str, lead_system_prompt: str = "") -> str:
    base = (lead_system_prompt + "\n\n") if lead_system_prompt else ""
    return (f"{base}You are the team lead refining work for project '{project_name}'. "
            "Converse with the user and propose epics, features, and tasks to draft onto the "
            "board. Features and tasks must reference an existing parent id. Everything you "
            "propose is created as a Draft for human review — never mark anything ready. "
            "You may also propose edits to EXISTING items (epics, features, or tasks) by "
            "returning `updates`, each with the item's id and any of title/body/"
            "acceptance_criteria — content only, never status. Proposed edits are shown to the "
            "human for approval before they apply. "
            "After you propose a breakdown, ask the user to confirm before starting; only when "
            "they approve in a later message, set action='commit' (with no new proposals) to "
            "promote the drafted tasks and start work. Never set action='commit' in the same "
            "turn you first propose the breakdown.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_refinement.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/domain/refinement.py tests/unit/test_refinement.py
git commit -m "feat: confirm-before-commit guidance in refinement system prompt"
```

---

## Task 3: `chat_session_id` on the WorkItem domain model

**Files:**
- Modify: `src/domain/projects/work_items.py`
- Test: `tests/unit/test_work_items.py` (create if absent; otherwise append)

- [ ] **Step 1: Write the failing test** — add:

```python
def test_work_item_carries_chat_session_id():
    from domain.projects import WorkItem, WorkItemKind

    item = WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.EPIC,
                    title="E", chat_session_id="s1")
    assert item.chat_session_id == "s1"


def test_work_item_chat_session_id_defaults_none():
    from domain.projects import WorkItem, WorkItemKind

    item = WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.EPIC, title="E")
    assert item.chat_session_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_work_items.py -k chat_session -v`
Expected: FAIL with `ValidationError` (unexpected keyword `chat_session_id`).

- [ ] **Step 3: Write minimal implementation** — add the field to `WorkItem` (after `assignee_agent_id`):

```python
    assignee_agent_id: str | None = None
    chat_session_id: str | None = None
    active: bool = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_work_items.py -k chat_session -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/domain/projects/work_items.py tests/unit/test_work_items.py
git commit -m "feat: WorkItem.chat_session_id provenance field"
```

---

## Task 4: Persistence column + migration

**Files:**
- Modify: `src/adapters/database/orm.py` (`WorkItemRow`)
- Create: `migrations/versions/chatsid01_work_item_chat_session_id.py`
- Test: `tests/unit/test_repositories.py`

- [ ] **Step 1: Write the failing test** — add (mirrors the existing owner-scoped repo test style):

```python
def test_work_item_chat_session_id_round_trips_and_filters():
    from adapters.database.engine import make_engine, make_session_factory
    from adapters.database.orm import Base
    from adapters.database.uow import SqlUnitOfWork
    from domain.projects import WorkItem, WorkItemKind, WorkItemStatus

    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        uow.work_items.create(WorkItem(owner_id="u1", project_id="p1",
                                       kind=WorkItemKind.EPIC, title="E",
                                       chat_session_id="s1"))
        uow.work_items.create(WorkItem(owner_id="u1", project_id="p1",
                                       kind=WorkItemKind.EPIC, title="other"))
        scoped = uow.work_items.list(filters={"project_id": "p1", "chat_session_id": "s1"})
    assert scoped.total == 1
    assert scoped.results[0].chat_session_id == "s1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_repositories.py -k chat_session_id -v`
Expected: FAIL — column missing (`chat_session_id` not a known attribute / not persisted).

- [ ] **Step 3a: Add the ORM column** — in `src/adapters/database/orm.py`, `WorkItemRow`, after `assignee_agent_id`:

```python
    assignee_agent_id: Mapped[str | None] = mapped_column(String(32), index=True)
    chat_session_id: Mapped[str | None] = mapped_column(String(32), index=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
```

- [ ] **Step 3b: Hand-write the migration** — create `migrations/versions/chatsid01_work_item_chat_session_id.py`:

```python
"""work_item chat_session_id

Revision ID: chatsid01
Revises: b6fcfb4dc8d2
Create Date: 2026-06-19

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "chatsid01"
down_revision: str | None = "b6fcfb4dc8d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "work_items",
        sa.Column("chat_session_id", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ix_work_items_chat_session_id", "work_items", ["chat_session_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_work_items_chat_session_id", table_name="work_items")
    op.drop_column("work_items", "chat_session_id")
```

> Confirm `b6fcfb4dc8d2` is still the alembic head before committing:
> `uv run alembic heads` should print `b6fcfb4dc8d2`. If a newer head exists (another branch merged), set `down_revision` to that id instead.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_repositories.py -k chat_session_id -v`
Expected: PASS (SQLite tests build schema from the ORM via `create_all`).

- [ ] **Step 5: Commit**

```bash
git add src/adapters/database/orm.py migrations/versions/chatsid01_work_item_chat_session_id.py tests/unit/test_repositories.py
git commit -m "feat: persist work_item.chat_session_id (+ migration)"
```

---

## Task 5: Fake agent commits on approval; lock Anthropic parse

**Files:**
- Modify: `src/adapters/agent/refinement/fake.py`
- Test: `tests/unit/test_refinement_agent.py`

- [ ] **Step 1: Write the failing test** — add:

```python
def test_fake_agent_commits_on_approval_token():
    from adapters.agent.refinement.fake import FakeRefinementAgent
    from domain.refinement import (
        ChatMessage, ChatRole, RefinementAction, RefinementContext,
    )

    ctx = RefinementContext(
        project_name="Alpha",
        history=[ChatMessage(owner_id="u", session_id="s", role=ChatRole.USER,
                             content="go")],
    )
    out = FakeRefinementAgent().respond(ctx)
    assert out.action == RefinementAction.COMMIT
    assert out.proposals == []


def test_fake_agent_discusses_by_default():
    from adapters.agent.refinement.fake import FakeRefinementAgent
    from domain.refinement import (
        ChatMessage, ChatRole, RefinementAction, RefinementContext,
    )

    ctx = RefinementContext(
        project_name="Alpha",
        history=[ChatMessage(owner_id="u", session_id="s", role=ChatRole.USER,
                             content="build login")],
    )
    out = FakeRefinementAgent().respond(ctx)
    assert out.action == RefinementAction.DISCUSS
    assert out.proposals  # still drafts an epic


def test_anthropic_output_parses_action_from_tool_input():
    # Lock-in: action flows through the schema-derived tool + RefinementOutput(**input).
    from domain.refinement import RefinementAction, RefinementOutput

    schema = RefinementOutput.model_json_schema()
    assert "action" in schema["properties"]
    out = RefinementOutput(**{"reply": "ok", "action": "commit"})
    assert out.action == RefinementAction.COMMIT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_refinement_agent.py -k "commit or action" -v`
Expected: FAIL — fake returns `DISCUSS` for "go" (no commit branch yet).

- [ ] **Step 3: Write minimal implementation** — rewrite `src/adapters/agent/refinement/fake.py`:

```python
from domain.projects import WorkItemKind
from domain.refinement import (
    EpicSpecEdit,
    RefinementAction,
    RefinementContext,
    RefinementOutput,
    WorkItemProposal,
)

_APPROVALS = ("go", "yes", "start", "ship", "approve", "do it")


class FakeRefinementAgent:
    """Deterministic. An approval message ('go'/'yes'/…) commits. Otherwise, unscoped:
    drafts one epic; epic-scoped: drafts a child feature and proposes an epic spec edit."""

    def respond(self, ctx: RefinementContext) -> RefinementOutput:
        last = next((m.content for m in reversed(ctx.history) if m.role == "user"), "work")
        if last.strip().lower().startswith(_APPROVALS):
            return RefinementOutput(
                reply="Starting the committed work.",
                action=RefinementAction.COMMIT,
            )
        title = last.strip()[:60] or "work"
        if ctx.epic_id:
            return RefinementOutput(
                reply=f"Refined the epic and drafted a feature for: {title}",
                proposals=[
                    WorkItemProposal(
                        kind=WorkItemKind.FEATURE, parent_id=ctx.epic_id, title=title
                    )
                ],
                epic_update=EpicSpecEdit(
                    body=f"Spec: {title}", acceptance_criteria=[f"{title} works"]
                ),
            )
        return RefinementOutput(
            reply=f"Drafted an epic for: {title}",
            proposals=[WorkItemProposal(kind=WorkItemKind.EPIC, title=title)],
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_refinement_agent.py -v`
Expected: PASS (existing agent tests still green — none start with an approval token).

- [ ] **Step 5: Commit**

```bash
git add src/adapters/agent/refinement/fake.py tests/unit/test_refinement_agent.py
git commit -m "feat: FakeRefinementAgent commits on approval; lock action parse"
```

---

## Task 6: Chat endpoint commit path

**Files:**
- Modify: `src/interactors/api/routes/chat.py`
- Test: `tests/integration/test_chat_api.py`

- [ ] **Step 1: Write the failing test** — add to `tests/integration/test_chat_api.py` (use a scripted agent so a session-tagged TASK exists to commit; mirror the `_FakeTemporal`/team setup from `test_backlog_api.py`):

```python
from interactors.api.deps import refinement_agent, temporal_client
from domain.projects import WorkItemKind
from domain.refinement import RefinementAction, RefinementOutput, WorkItemProposal


class _FakeTemporal:
    def __init__(self):
        self.started = []

    def start_run_workflow(self, run_input, workflow_name="OrchestratorWorkflow"):
        self.started.append((workflow_name, run_input))

    def signal(self, run_id, name):  # pragma: no cover - unused
        pass


class _ScriptedAgent:
    """Turn 1: draft a task under the given parent. Turn 2+: commit."""

    def __init__(self, parent_id):
        self.parent_id = parent_id
        self.calls = 0

    def respond(self, ctx):
        self.calls += 1
        if self.calls == 1:
            return RefinementOutput(
                reply="drafted a task — confirm to start",
                proposals=[WorkItemProposal(kind=WorkItemKind.TASK,
                                            parent_id=self.parent_id, title="T")],
            )
        return RefinementOutput(reply="starting", action=RefinementAction.COMMIT)


def test_commit_starts_a_run_for_session_drafted_task():
    # One app/client throughout so the in-memory SQLite DB is shared across requests.
    # Build the app first so we can create the epic, THEN wire the scripted agent to it.
    app = create_app(Settings(_env_file=None, database_url="sqlite:///:memory:"))
    fake = _FakeTemporal()
    app.dependency_overrides[temporal_client] = lambda: fake
    c = TestClient(app)

    pid = c.post("/projects", json={"name": "p", "repo_url": "r"}).json()["data"]["id"]
    team_id = c.post("/teams/default").json()["data"]["team"]["id"]
    c.patch(f"/projects/{pid}", json={"team_id": team_id})
    epic = c.post(f"/projects/{pid}/work-items",
                  json={"kind": "epic", "title": "E"}).json()["data"]

    app.dependency_overrides[refinement_agent] = lambda: _ScriptedAgent(epic["id"])

    # Turn 1: draft a task (DRAFT, tagged with the session). No runs yet.
    r1 = c.post(f"/projects/{pid}/chat", json={"message": "break it down"}).json()["data"]
    sid = r1["session_id"]
    assert len(r1["created_items"]) == 1
    assert r1["created_items"][0]["status"] == "draft"
    assert fake.started == []

    # Turn 2: approve → commit. Task promoted to READY, epic activated, run started.
    r2 = c.post(f"/projects/{pid}/chat",
                json={"message": "go", "session_id": sid}).json()["data"]
    assert len(fake.started) == 1
    workflow_name, run_input = fake.started[0]
    assert workflow_name == "OrchestratorWorkflow"
    assert run_input["task_id"] == r1["created_items"][0]["id"]
    assert run_input["task_title"] == "T"
    assert r2["started_runs"] == [run_input["run_id"]]


def test_commit_with_nothing_to_start_is_noop():
    app = create_app(Settings(_env_file=None, database_url="sqlite:///:memory:"))
    fake = _FakeTemporal()
    app.dependency_overrides[temporal_client] = lambda: fake

    class _CommitOnly:
        def respond(self, ctx):
            return RefinementOutput(reply="ok", action=RefinementAction.COMMIT)

    app.dependency_overrides[refinement_agent] = lambda: _CommitOnly()
    c = TestClient(app)
    pid = c.post("/projects", json={"name": "p", "repo_url": "r"}).json()["data"]["id"]

    r = c.post(f"/projects/{pid}/chat", json={"message": "go"})
    assert r.status_code == 200
    assert r.json()["data"]["started_runs"] == []
    assert fake.started == []
```

> Shared-DB pitfall: use a single `app`/`TestClient` for the whole flow. Building two apps gives two separate in-memory SQLite databases, so the second request won't see the first's rows.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_chat_api.py -k "commit" -v`
Expected: FAIL — `started_runs` key missing and no run started (commit path not implemented).

- [ ] **Step 3: Write minimal implementation** — edit `src/interactors/api/routes/chat.py`:

(a) Extend imports:

```python
from domain.base import utc_now
from domain.projects import WorkItem, WorkItemKind, WorkItemStatus
from domain.refinement import (
    ChatMessage,
    ChatRole,
    ChatSession,
    RefinementAction,
    RefinementContext,
    epic_focus_prompt,
    select_committable,
    system_prompt,
    validate_proposal,
)
from domain.transitions import InvalidTransition, validate_transition
from interactors.api.deps import get_uow, refinement_agent, temporal_client
from interactors.api.deps import settings as get_settings
from interactors.api.envelope import ok
from interactors.scheduling import reconcile_project
from interactors.temporal.client import TemporalRunClient
```

(b) Add `settings` + `temporal` deps to the endpoint signature:

```python
@router.post("/projects/{project_id}/chat")
def post_message(
    project_id: str,
    body: PostMessage,
    uow: UnitOfWork = Depends(get_uow),
    agent: RefinementAgent = Depends(refinement_agent),
    temporal: TemporalRunClient = Depends(temporal_client),
    settings=Depends(get_settings),
) -> dict:
```

(c) Tag created items with the session — in the proposal loop, add `chat_session_id=session.id`:

```python
            item = uow.work_items.create(
                WorkItem(
                    project_id=project_id,
                    owner_id=project.owner_id,
                    kind=proposal.kind,
                    parent_id=proposal.parent_id,
                    title=proposal.title,
                    body=proposal.body,
                    acceptance_criteria=proposal.acceptance_criteria,
                    status=WorkItemStatus.DRAFT,  # NEVER ready
                    chat_session_id=session.id,
                )
            )
```

(d) After the `proposed_updates` loop and before `reply = out.reply + ...`, add the commit path (still inside `with uow.transaction():`):

```python
        run_inputs: list[dict] = []
        if out.action == RefinementAction.COMMIT:
            session_items = uow.work_items.list(
                filters={"project_id": project_id, "chat_session_id": session.id},
                page_size=500,
            ).results
            plan = select_committable(session_items)
            by_id = {i.id: i for i in session_items}
            for tid in plan.task_ids:
                task = by_id[tid]
                try:
                    validate_transition(task.status, WorkItemStatus.READY)
                except InvalidTransition as exc:
                    notes.append(str(exc))
                    continue
                uow.work_items.update(
                    tid,
                    task.model_copy(
                        update={"status": WorkItemStatus.READY, "updated_at": utc_now()}
                    ),
                )
            for pid in plan.parent_ids:
                parent = uow.work_items.get(pid)
                if parent.kind in (WorkItemKind.EPIC, WorkItemKind.FEATURE) and not parent.active:
                    uow.work_items.update(
                        pid,
                        parent.model_copy(update={"active": True, "updated_at": utc_now()}),
                    )
            run_inputs = reconcile_project(uow, settings, project_id)
```

(e) Launch runs after the transaction and surface them in the response:

```python
        reply = out.reply + (("\n\nSkipped: " + "; ".join(notes)) if notes else "")

    for ri in run_inputs:
        temporal.start_run_workflow(ri, "OrchestratorWorkflow")

    return ok(
        {
            "session_id": session.id,
            "reply": reply,
            "created_items": [c.model_dump(mode="json") for c in created],
            "proposed_epic_update": proposed_epic_update,
            "proposed_updates": proposed_updates,
            "started_runs": [ri["run_id"] for ri in run_inputs],
        }
    )
```

> Note: `run_inputs` is initialized inside the transaction; reference it after the `with` block (it stays in scope). Keep the `temporal.start_run_workflow` loop OUTSIDE the transaction (DB commits first, Temporal after) — same ordering as `activate_item`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_chat_api.py -v`
Expected: PASS — including the existing `discuss` tests (regression guard).

- [ ] **Step 5: Commit**

```bash
git add src/interactors/api/routes/chat.py tests/integration/test_chat_api.py
git commit -m "feat: chat commit path promotes tasks, activates parents, starts runs"
```

---

## Task 7: Full verify + integration PR

- [ ] **Step 1: Full suite + coverage gate**

Run: `rm -rf ui/dist && uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80`
Expected: PASS, ≥80%.

- [ ] **Step 2: Lint**

Run: `uv run ruff check src tests` (or `make lint`)
Expected: clean.

- [ ] **Step 3: Migration smoke (Postgres)** — verify upgrade/downgrade apply cleanly:

```bash
docker compose up -d postgres
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```
Expected: no errors; `work_items.chat_session_id` added then dropped then re-added.

- [ ] **Step 4: Push + open PR**

```bash
git push -u origin feat/chat-commit-autorun
gh pr create --title "feat: chat-driven commit → auto-run" \
  --body "Lets the refinement chat promote drafted tasks and auto-start runs on a natural-language 'go'. See docs/plans/2026-06-19-yaah-chat-commit-autorun-design.md."
```

---

## Self-review (resolved)

- **Spec coverage:** `action` field ↔ T1; confirm-before-commit prompt ↔ T2; `chat_session_id` domain ↔ T3 / persistence + migration ↔ T4; `select_committable` ↔ T1; commit path (promote + activate + reconcile + launch) ↔ T6; Fake commit + Anthropic auto-flow ↔ T5; error/edge cases (nothing-to-start, invalid transition skip, concurrency cap, launch-after-commit) ↔ T6 tests + reuse of `reconcile_project`. ✅
- **No new run-start machinery:** commit reuses `reconcile_project` + `start_run_workflow("OrchestratorWorkflow")`, identical to `activate_item`. ✅
- **Type consistency:** `RefinementAction`/`RefinementOutput.action` (T1) consumed in fake (T5) + endpoint (T6); `CommitPlan.task_ids`/`parent_ids` (T1) consumed by endpoint (T6); `select_committable` signature `list[WorkItem] -> CommitPlan` consistent T1↔T6; `chat_session_id` field (T3) ↔ column (T4) ↔ created-item tag + filter (T6); `validate_transition`/`InvalidTransition` import (T6) match `domain/transitions`. ✅
- **Regression guard:** `discuss` turns still create DRAFT only and start nothing (existing tests untouched; new `test_commit_with_nothing_to_start_is_noop` + default-discuss fake test). ✅
- **Gated:** commit only ever moves DRAFT→READY via `validate_transition`; run-stage PR/PLAN gates unchanged. ✅
