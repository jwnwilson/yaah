# Epic Spec & Breakdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user spec out an epic with the team lead and break it into Draft features/tasks, viewed through a board-integrated epic context band, an epic-scoped lead chat, and a lead-proposed epic-spec edit.

**Architecture:** Hexagonal — a pure `domain/epics.py` read-model (`build_epic_board`) feeds a new aggregation endpoint; the refinement contract gains epic focus + an optional `epic_update`; the chat route narrows context to the selected epic's subtree and surfaces (never auto-applies) the proposed epic edit. The board UI gains an `EpicContextBand` driven by the aggregation endpoint, epic selection state, and an accept/reject card in the chat rail. No schema changes.

**Tech Stack:** Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2.0 (SQLite in-memory for tests) · pytest + httpx · React + Vite + TanStack Query · vitest + msw. Package managers: `uv` (backend), `pnpm` (UI, from `ui/`).

**Reference spec:** `docs/specs/2026-06-15-epic-spec-and-breakdown-design.md`

**Conventions:** `{success,data,error}` envelope via `interactors/api/envelope.ok`. Pydantic models updated via `model_copy(update=…)` (never mutated). Owner-scoping handled by the UnitOfWork. Commit after each task with `<type>: <description>`. Run backend tests with `uv run pytest`; UI tests with `cd ui && pnpm vitest run <path>` (never `pnpm test -- <path>`).

---

## File Structure

**Backend**
- Create `src/domain/epics.py` — pure read-model: `FeatureProgress`, `EpicBoard`, `build_epic_board`.
- Modify `src/domain/refinement.py` — add `EpicSpecEdit`, `RefinementContext.epic_id`, `RefinementOutput.epic_update`, `epic_focus_prompt`.
- Modify `src/adapters/agent/refinement/fake.py` — branch on `ctx.epic_id`.
- Create `src/interactors/api/routes/epics.py` — `GET /projects/{project_id}/epics/{epic_id}/board`.
- Modify `src/interactors/api/app.py` — register the epics router.
- Modify `src/interactors/api/routes/chat.py` — epic-scoped narrowing + surface `proposed_epic_update`.

**Tests (backend)**
- Create `tests/unit/test_epic_board.py`
- Create `tests/unit/test_refinement_epic_focus.py`
- Create `tests/integration/test_epic_board_api.py`
- Modify `tests/integration/test_chat_api.py`

**Frontend** (all under `ui/src/`)
- Create `lib/api/epics.ts` — `EpicBoard` types, `epicKeys`, `getEpicBoard`.
- Modify `lib/api/chat.ts` — `EpicSpecEdit`, `proposed_epic_update`, `epic_id` arg.
- Create `modules/board/useEpicBoard.ts`
- Create `modules/board/EpicContextBand.tsx`
- Modify `modules/board/Board.tsx` — optional `items` prop.
- Modify `modules/board/BoardPage.tsx` — epic selection + band wiring.
- Modify `modules/work-items/HierarchyTree.tsx` — epic selection.
- Modify `modules/chat/useChat.ts` — epic scoping + proposed-edit accept/dismiss.
- Modify `modules/chat/ChatRail.tsx` — `epicId` prop + accept/reject card.

**Tests (UI)**
- Create `modules/board/EpicContextBand.test.tsx`
- Modify `modules/chat/ChatRail.test.tsx`

---

## Task 1: Domain read-model `build_epic_board`

**Files:**
- Create: `src/domain/epics.py`
- Test: `tests/unit/test_epic_board.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_epic_board.py
"""Unit tests for the pure epic-board read-model."""
from domain.epics import build_epic_board
from domain.models import WorkItem, WorkItemKind, WorkItemStatus


def _epic() -> WorkItem:
    return WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.EPIC, title="E")


def _feature(epic_id: str, title: str) -> WorkItem:
    return WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.FEATURE,
                    parent_id=epic_id, title=title)


def _task(parent_id: str, status: WorkItemStatus = WorkItemStatus.DRAFT) -> WorkItem:
    return WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.TASK,
                    parent_id=parent_id, title="t", status=status)


def test_groups_tasks_under_features_with_done_counts():
    epic = _epic()
    f1 = _feature(epic.id, "Cart")
    tasks = [_task(f1.id, WorkItemStatus.DONE), _task(f1.id)]
    board = build_epic_board(epic, [f1], tasks)
    assert board.epic.id == epic.id
    assert board.features[0].feature.id == f1.id
    assert board.features[0].total == 2
    assert board.features[0].done == 1


def test_total_counts_include_tasks_parented_directly_to_epic():
    epic = _epic()
    f1 = _feature(epic.id, "Cart")
    tasks = [_task(f1.id, WorkItemStatus.DONE), _task(epic.id, WorkItemStatus.DONE)]
    board = build_epic_board(epic, [f1], tasks)
    assert board.total == 2
    assert board.done == 2
    # direct-to-epic task is not counted under any feature
    assert board.features[0].total == 1


def test_empty_epic_has_zero_counts_and_no_features():
    epic = _epic()
    board = build_epic_board(epic, [], [])
    assert board.features == []
    assert board.total == 0 and board.done == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_epic_board.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domain.epics'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/domain/epics.py
"""Pure epic-board read-model: groups an epic's features/tasks and counts progress. No I/O."""
from collections import defaultdict

from pydantic import BaseModel

from domain.models import WorkItem, WorkItemStatus


class FeatureProgress(BaseModel):
    feature: WorkItem
    total: int
    done: int


class EpicBoard(BaseModel):
    epic: WorkItem
    features: list[FeatureProgress]
    tasks: list[WorkItem]
    total: int
    done: int


def build_epic_board(
    epic: WorkItem, features: list[WorkItem], tasks: list[WorkItem]
) -> EpicBoard:
    by_parent: dict[str | None, list[WorkItem]] = defaultdict(list)
    for task in tasks:
        by_parent[task.parent_id].append(task)

    feature_progress = [
        FeatureProgress(
            feature=feature,
            total=len(by_parent.get(feature.id, [])),
            done=sum(
                1 for t in by_parent.get(feature.id, []) if t.status == WorkItemStatus.DONE
            ),
        )
        for feature in features
    ]
    return EpicBoard(
        epic=epic,
        features=feature_progress,
        tasks=tasks,
        total=len(tasks),
        done=sum(1 for t in tasks if t.status == WorkItemStatus.DONE),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_epic_board.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/domain/epics.py tests/unit/test_epic_board.py
git commit -m "feat: pure epic-board read-model (build_epic_board)"
```

---

## Task 2: Epic-board aggregation endpoint

**Files:**
- Create: `src/interactors/api/routes/epics.py`
- Modify: `src/interactors/api/app.py` (router imports near line 67; `include_router` calls near line 78-91)
- Test: `tests/integration/test_epic_board_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_epic_board_api.py
"""Integration tests for the epic-board aggregation endpoint."""
from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def _client():
    return TestClient(create_app(Settings(_env_file=None, database_url="sqlite:///:memory:")))


def _project(c) -> str:
    return c.post("/projects", json={"name": "Alpha", "repo_url": "r"}).json()["data"]["id"]


def _item(c, pid, kind, title, parent_id=None) -> dict:
    return c.post(
        f"/projects/{pid}/work-items",
        json={"kind": kind, "title": title, "parent_id": parent_id},
    ).json()["data"]


def test_epic_board_returns_subtree_with_counts():
    c = _client()
    pid = _project(c)
    epic = _item(c, pid, "epic", "Checkout")
    feature = _item(c, pid, "feature", "Cart", parent_id=epic["id"])
    t1 = _item(c, pid, "task", "t1", parent_id=feature["id"])
    _item(c, pid, "task", "t2", parent_id=feature["id"])

    # move t1 to done so a count is non-zero
    c.post(f"/work-items/{t1['id']}/status", json={"status": "ready"})
    c.post(f"/work-items/{t1['id']}/status", json={"status": "in_progress"})
    c.post(f"/work-items/{t1['id']}/status", json={"status": "in_review"})
    c.post(f"/work-items/{t1['id']}/status", json={"status": "approved"})
    c.post(f"/work-items/{t1['id']}/status", json={"status": "done"})

    r = c.get(f"/projects/{pid}/epics/{epic['id']}/board")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["epic"]["id"] == epic["id"]
    assert data["total"] == 2 and data["done"] == 1
    assert data["features"][0]["feature"]["id"] == feature["id"]
    assert data["features"][0]["total"] == 2 and data["features"][0]["done"] == 1
    assert {t["id"] for t in data["tasks"]} == {t1["id"], data["tasks"][1]["id"]}


def test_empty_epic_returns_zero_counts():
    c = _client()
    pid = _project(c)
    epic = _item(c, pid, "epic", "Lonely")
    data = c.get(f"/projects/{pid}/epics/{epic['id']}/board").json()["data"]
    assert data["features"] == [] and data["total"] == 0 and data["done"] == 0


def test_unknown_epic_returns_404():
    c = _client()
    pid = _project(c)
    r = c.get(f"/projects/{pid}/epics/nope/board")
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_epic_board_api.py -v`
Expected: FAIL with 404 on a valid epic (route not registered) / collection passes but assertions fail.

- [ ] **Step 3: Write minimal implementation**

```python
# src/interactors/api/routes/epics.py
from fastapi import APIRouter, Depends

from adapters.database.ports import UnitOfWork
from domain.epics import build_epic_board
from domain.models import WorkItemKind
from interactors.api.deps import get_uow
from interactors.api.envelope import ok

router = APIRouter(tags=["epics"])


@router.get("/projects/{project_id}/epics/{epic_id}/board")
def epic_board(
    project_id: str, epic_id: str, uow: UnitOfWork = Depends(get_uow)
) -> dict:
    with uow.transaction():
        uow.projects.get(project_id)  # RecordNotFound -> 404
        epic = uow.work_items.get(epic_id)  # owner-scoped; RecordNotFound -> 404
        features = uow.work_items.list(
            filters={"project_id": project_id, "parent_id": epic_id, "kind": WorkItemKind.FEATURE},
            page_size=200,
        ).results
        parent_ids = [epic_id, *(f.id for f in features)]
        tasks = [
            t
            for parent_id in parent_ids
            for t in uow.work_items.list(
                filters={"project_id": project_id, "parent_id": parent_id, "kind": WorkItemKind.TASK},
                page_size=200,
            ).results
        ]
        board = build_epic_board(epic, features, tasks)
    return ok(board.model_dump(mode="json"))
```

Then register the router in `src/interactors/api/app.py`. Add `epics` to the route import block (the tuple/import near line 67 alongside `chat`, `work_items`), and add this line next to the other `include_router` calls (after line 91):

```python
    app.include_router(epics.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_epic_board_api.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/interactors/api/routes/epics.py src/interactors/api/app.py tests/integration/test_epic_board_api.py
git commit -m "feat: epic-board aggregation endpoint"
```

---

## Task 3: Refinement contract — epic focus + epic_update

**Files:**
- Modify: `src/domain/refinement.py`
- Test: `tests/unit/test_refinement_epic_focus.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_refinement_epic_focus.py
"""Unit tests for epic-focused refinement contract additions."""
from domain.models import WorkItem, WorkItemKind
from domain.refinement import (
    EpicSpecEdit,
    RefinementContext,
    RefinementOutput,
    epic_focus_prompt,
)


def test_epic_focus_prompt_names_epic_and_instructs_breakdown():
    epic = WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.EPIC, title="Checkout")
    prompt = epic_focus_prompt(epic)
    assert "Checkout" in prompt
    assert epic.id in prompt
    assert "feature" in prompt.lower()


def test_refinement_output_parses_epic_update():
    out = RefinementOutput(**{"reply": "ok", "epic_update": {"body": "new", "acceptance_criteria": ["a"]}})
    assert isinstance(out.epic_update, EpicSpecEdit)
    assert out.epic_update.body == "new"
    assert out.epic_update.acceptance_criteria == ["a"]


def test_refinement_output_epic_update_defaults_none():
    assert RefinementOutput(reply="hi").epic_update is None


def test_refinement_context_carries_epic_id():
    ctx = RefinementContext(project_name="p", epic_id="e1")
    assert ctx.epic_id == "e1"
    assert RefinementContext(project_name="p").epic_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_refinement_epic_focus.py -v`
Expected: FAIL with `ImportError: cannot import name 'EpicSpecEdit'`

- [ ] **Step 3: Write minimal implementation**

In `src/domain/refinement.py`, add the `EpicSpecEdit` model after `WorkItemProposal` (after line 15):

```python
class EpicSpecEdit(BaseModel):
    body: str | None = None
    acceptance_criteria: list[str] | None = None
```

Add `epic_id` to `RefinementContext` (after the `system_prompt` field, line 25):

```python
    epic_id: str | None = None
```

Add `epic_update` to `RefinementOutput` (after the `proposals` field, line 30):

```python
    epic_update: EpicSpecEdit | None = None
```

Add the focus-prompt builder at the end of the file (after `system_prompt`):

```python
def epic_focus_prompt(epic: WorkItem) -> str:
    return (
        f"You are now refining the epic '{epic.title}' (id {epic.id}). Propose features "
        f"under this epic (parent_id={epic.id}) and tasks under those features. You may also "
        "return an epic_update to refine THIS epic's body and acceptance criteria. Everything "
        "is created as a Draft for human review — never mark anything ready."
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_refinement_epic_focus.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/domain/refinement.py tests/unit/test_refinement_epic_focus.py
git commit -m "feat: epic-focus refinement contract (epic_update + epic_id + focus prompt)"
```

---

## Task 4: Fake refinement agent honors epic scope

**Files:**
- Modify: `src/adapters/agent/refinement/fake.py`
- Test: `tests/unit/test_refinement_agent.py` (append a test)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_refinement_agent.py`:

```python
def test_fake_agent_proposes_feature_and_epic_update_when_epic_scoped():
    from domain.models import ChatMessage, ChatRole
    from domain.refinement import RefinementContext
    from adapters.agent.refinement.fake import FakeRefinementAgent

    ctx = RefinementContext(
        project_name="p",
        epic_id="epic-1",
        history=[ChatMessage(owner_id="u", session_id="s", role=ChatRole.USER, content="cart flow")],
    )
    out = FakeRefinementAgent().respond(ctx)
    assert out.epic_update is not None
    assert out.proposals and out.proposals[0].parent_id == "epic-1"
    assert out.proposals[0].kind == "feature"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_refinement_agent.py::test_fake_agent_proposes_feature_and_epic_update_when_epic_scoped -v`
Expected: FAIL — `out.epic_update is None` (fake ignores `epic_id`).

- [ ] **Step 3: Write minimal implementation**

Replace the body of `src/adapters/agent/refinement/fake.py`:

```python
from domain.models import WorkItemKind
from domain.refinement import (
    EpicSpecEdit,
    RefinementContext,
    RefinementOutput,
    WorkItemProposal,
)


class FakeRefinementAgent:
    """Deterministic. Unscoped: drafts one epic. Epic-scoped: drafts a child feature and
    proposes an epic spec edit."""

    def respond(self, ctx: RefinementContext) -> RefinementOutput:
        last = next((m.content for m in reversed(ctx.history) if m.role == "user"), "work")
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
Expected: PASS (existing tests + the new one)

- [ ] **Step 5: Commit**

```bash
git add src/adapters/agent/refinement/fake.py tests/unit/test_refinement_agent.py
git commit -m "feat: fake refinement agent honors epic scope"
```

---

## Task 5: Chat route — epic-scoped narrowing + surface proposed edit

**Files:**
- Modify: `src/interactors/api/routes/chat.py`
- Test: `tests/integration/test_chat_api.py` (append tests)

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/test_chat_api.py`:

```python
def _make_epic(c, pid) -> str:
    return c.post(
        f"/projects/{pid}/work-items", json={"kind": "epic", "title": "Checkout"}
    ).json()["data"]["id"]


def test_epic_scoped_chat_drafts_child_feature_and_returns_proposed_update():
    c = _client()
    pid = _project(c)
    epic_id = _make_epic(c, pid)
    r = c.post(f"/projects/{pid}/chat", json={"message": "cart flow", "epic_id": epic_id})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["proposed_epic_update"] is not None
    assert data["proposed_epic_update"]["body"]
    # the child feature was drafted under the epic
    assert data["created_items"][0]["kind"] == "feature"
    assert data["created_items"][0]["parent_id"] == epic_id


def test_unscoped_chat_has_no_proposed_epic_update():
    c = _client()
    pid = _project(c)
    data = c.post(f"/projects/{pid}/chat", json={"message": "build login"}).json()["data"]
    assert data["proposed_epic_update"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_chat_api.py -k epic_scoped -v`
Expected: FAIL with `KeyError: 'proposed_epic_update'`

- [ ] **Step 3: Write minimal implementation**

In `src/interactors/api/routes/chat.py`:

Update the imports — add `WorkItemKind` to the `domain.models` import and `epic_focus_prompt` to the `domain.refinement` import:

```python
from domain.models import ChatMessage, ChatRole, ChatSession, WorkItem, WorkItemKind, WorkItemStatus
from domain.refinement import RefinementContext, epic_focus_prompt, system_prompt, validate_proposal
```

Replace the hierarchy/context block (currently lines 58-68 — the `hierarchy = uow.work_items.list(...)` call through `out = agent.respond(ctx)`) with:

```python
        epic_scope = session.epic_id
        if epic_scope:
            epic = uow.work_items.get(epic_scope)
            features = uow.work_items.list(
                filters={"project_id": project_id, "parent_id": epic.id, "kind": WorkItemKind.FEATURE},
                page_size=200,
            ).results
            parent_ids = [epic.id, *(f.id for f in features)]
            tasks = [
                t
                for parent_id in parent_ids
                for t in uow.work_items.list(
                    filters={"project_id": project_id, "parent_id": parent_id, "kind": WorkItemKind.TASK},
                    page_size=200,
                ).results
            ]
            hierarchy = [epic, *features, *tasks]
            prompt = system_prompt(project.name) + "\n\n" + epic_focus_prompt(epic)
        else:
            hierarchy = uow.work_items.list(
                filters={"project_id": project_id}, page_size=200
            ).results
            prompt = system_prompt(project.name)

        ctx = RefinementContext(
            project_name=project.name,
            history=history,
            hierarchy=hierarchy,
            system_prompt=prompt,
            epic_id=epic_scope,
        )
        out = agent.respond(ctx)
```

After the proposal-creation loop, before computing `reply` (currently line 109), add:

```python
        proposed_epic_update = (
            out.epic_update.model_dump(mode="json")
            if epic_scope and out.epic_update
            else None
        )
```

Add `proposed_epic_update` to the returned dict (in the `ok({...})` near line 111):

```python
    return ok(
        {
            "session_id": session.id,
            "reply": reply,
            "created_items": [c.model_dump(mode="json") for c in created],
            "proposed_epic_update": proposed_epic_update,
        }
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_chat_api.py -v`
Expected: PASS (existing chat tests + 2 new)

- [ ] **Step 5: Commit**

```bash
git add src/interactors/api/routes/chat.py tests/integration/test_chat_api.py
git commit -m "feat: epic-scoped refinement chat surfaces proposed epic edit"
```

---

## Task 6: Backend gate

- [ ] **Step 1: Run the full backend suite + coverage gate**

Run: `make coverage`
Expected: all tests pass; coverage ≥ 80%.

- [ ] **Step 2: Run the linter**

Run: `make lint`
Expected: clean.

(No commit — gate only. Fix any failures in the relevant task's files and re-run.)

---

## Task 7: UI API client — epics + chat extensions

**Files:**
- Create: `ui/src/lib/api/epics.ts`
- Modify: `ui/src/lib/api/chat.ts`

- [ ] **Step 1: Create the epics client**

```typescript
// ui/src/lib/api/epics.ts
import { apiGet } from "./client";
import type { WorkItem } from "./types";

export interface FeatureProgress {
  feature: WorkItem;
  total: number;
  done: number;
}

export interface EpicBoard {
  epic: WorkItem;
  features: FeatureProgress[];
  tasks: WorkItem[];
  total: number;
  done: number;
}

export const epicKeys = {
  board: (epicId: string) => ["epic-board", epicId] as const,
};

export async function getEpicBoard(projectId: string, epicId: string): Promise<EpicBoard> {
  return apiGet<EpicBoard>(`/projects/${projectId}/epics/${epicId}/board`);
}
```

- [ ] **Step 2: Extend the chat client**

In `ui/src/lib/api/chat.ts`, add the `EpicSpecEdit` interface, extend `ChatTurn`, and add the `epicId` argument to `postChat`:

```typescript
export interface EpicSpecEdit {
  body?: string | null;
  acceptance_criteria?: string[] | null;
}

export interface ChatTurn {
  session_id: string;
  reply: string;
  created_items: unknown[];
  proposed_epic_update?: EpicSpecEdit | null;
}

export async function postChat(
  projectId: string,
  message: string,
  sessionId?: string,
  epicId?: string,
): Promise<ChatTurn> {
  return apiPost<ChatTurn>(`/projects/${projectId}/chat`, {
    message,
    session_id: sessionId,
    epic_id: epicId,
  });
}
```

(Replace the existing `ChatTurn` interface and `postChat` function; keep `ChatMessage`, `chatKeys`, and `listMessages` unchanged.)

- [ ] **Step 3: Verify it compiles**

Run: `cd ui && pnpm lint`
Expected: no type errors.

- [ ] **Step 4: Commit**

```bash
git add ui/src/lib/api/epics.ts ui/src/lib/api/chat.ts
git commit -m "feat: UI epic-board client + chat epic scoping types"
```

---

## Task 8: `useEpicBoard` hook + `EpicContextBand`

**Files:**
- Create: `ui/src/modules/board/useEpicBoard.ts`
- Create: `ui/src/modules/board/EpicContextBand.tsx`
- Test: `ui/src/modules/board/EpicContextBand.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// ui/src/modules/board/EpicContextBand.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "@/test/server";
import { EpicContextBand } from "./EpicContextBand";

function renderBand(props: Partial<Parameters<typeof EpicContextBand>[0]> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <EpicContextBand
        projectId="p1"
        epicId="e1"
        selectedFeature={undefined}
        onSelectFeature={() => {}}
        onEditEpic={() => {}}
        {...props}
      />
    </QueryClientProvider>,
  );
}

const board = {
  epic: { id: "e1", title: "Checkout", status: "refining", body: "spec text" },
  features: [{ feature: { id: "f1", title: "Cart" }, total: 3, done: 1 }],
  tasks: [],
  total: 3,
  done: 1,
};

test("renders epic progress and feature chips", async () => {
  server.use(
    http.get("/api/projects/p1/epics/e1/board", () =>
      HttpResponse.json({ success: true, error: null, data: board })),
  );
  renderBand();
  await waitFor(() => expect(screen.getByText("Checkout")).toBeInTheDocument());
  expect(screen.getByText(/1\/3 tasks done/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Cart 1\/3/ })).toBeInTheDocument();
});

test("clicking a feature chip calls onSelectFeature", async () => {
  server.use(
    http.get("/api/projects/p1/epics/e1/board", () =>
      HttpResponse.json({ success: true, error: null, data: board })),
  );
  const onSelectFeature = vi.fn();
  renderBand({ onSelectFeature });
  await waitFor(() => screen.getByRole("button", { name: /Cart 1\/3/ }));
  await userEvent.click(screen.getByRole("button", { name: /Cart 1\/3/ }));
  expect(onSelectFeature).toHaveBeenCalledWith("f1");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && pnpm vitest run src/modules/board/EpicContextBand.test.tsx`
Expected: FAIL — cannot resolve `./EpicContextBand`.

- [ ] **Step 3: Write the hook and component**

```typescript
// ui/src/modules/board/useEpicBoard.ts
import { useQuery } from "@tanstack/react-query";
import { epicKeys, getEpicBoard } from "@/lib/api/epics";

export function useEpicBoard(projectId: string, epicId: string | undefined) {
  return useQuery({
    queryKey: epicId ? epicKeys.board(epicId) : (["epic-board", "none"] as const),
    queryFn: () => getEpicBoard(projectId, epicId as string),
    enabled: Boolean(epicId),
  });
}
```

```tsx
// ui/src/modules/board/EpicContextBand.tsx
import { useEpicBoard } from "./useEpicBoard";

interface EpicContextBandProps {
  projectId: string;
  epicId: string;
  selectedFeature: string | undefined;
  onSelectFeature: (featureId: string | undefined) => void;
  onEditEpic: (epicId: string) => void;
}

export function EpicContextBand({
  projectId,
  epicId,
  selectedFeature,
  onSelectFeature,
  onEditEpic,
}: EpicContextBandProps) {
  const { data } = useEpicBoard(projectId, epicId);
  if (!data) return null;
  const { epic, features, total, done } = data;

  const chip = (active: boolean) =>
    `rounded px-2 py-0.5 text-xs ${active ? "bg-accent text-accent-fg" : "bg-panel text-muted hover:text-fg"}`;

  return (
    <div className="border-b border-line bg-surface px-4 py-2">
      <div className="flex items-center gap-2">
        <button className="font-semibold text-fg hover:underline" onClick={() => onEditEpic(epic.id)}>
          {epic.title}
        </button>
        <span className="text-xs text-muted">[{epic.status}]</span>
        <span className="text-xs text-muted">{done}/{total} tasks done</span>
      </div>
      {epic.body && <p className="mt-1 line-clamp-1 text-xs text-muted">{epic.body}</p>}
      <div className="mt-2 flex flex-wrap gap-1">
        <button className={chip(!selectedFeature)} onClick={() => onSelectFeature(undefined)}>
          All tasks
        </button>
        {features.length === 0 && (
          <span className="text-xs text-muted">No features yet — ask the lead to break this epic down.</span>
        )}
        {features.map((fp) => (
          <button
            key={fp.feature.id}
            className={chip(selectedFeature === fp.feature.id)}
            onClick={() => onSelectFeature(fp.feature.id)}
          >
            {fp.feature.title} {fp.done}/{fp.total}
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && pnpm vitest run src/modules/board/EpicContextBand.test.tsx`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add ui/src/modules/board/useEpicBoard.ts ui/src/modules/board/EpicContextBand.tsx ui/src/modules/board/EpicContextBand.test.tsx
git commit -m "feat: epic context band + useEpicBoard hook"
```

---

## Task 9: Board accepts an explicit items list

**Files:**
- Modify: `ui/src/modules/board/Board.tsx`

- [ ] **Step 1: Add the optional `items` prop**

Replace the `Board` signature and the `data` derivation (lines 8-9) so a caller can supply an explicit task list (used for epic-scoped rendering); the `useBoardItems` path stays the default. Add the `WorkItem` type import at the top:

```typescript
import type { WorkItem, WorkItemStatus } from "@/lib/api/types";
```

```typescript
export function Board({
  projectId,
  parentId,
  items,
  onOpen,
}: {
  projectId: string;
  parentId?: string;
  items?: WorkItem[];
  onOpen?: (id: string) => void;
}) {
  const query = useBoardItems(projectId, parentId, items === undefined);
  const data = items ?? query.data;
  const isLoading = items === undefined && query.isLoading;
  const isError = items === undefined && query.isError;
  const error = query.error;
```

(The rest of the component body is unchanged — it already reads `data`, `isLoading`, `isError`, `error`.)

- [ ] **Step 2: Add an `enabled` flag to `useBoardItems`**

In `ui/src/modules/board/useBoardItems.ts`, accept and forward an `enabled` argument so the list query is skipped when the board renders from an explicit `items` array:

```typescript
import { useQuery } from "@tanstack/react-query";
import { listWorkItems, workItemKeys, type WorkItemFilters } from "@/lib/api/workItems";

export function useBoardItems(projectId: string, parentId?: string, enabled = true) {
  const filters: WorkItemFilters = { kind: "task", parent_id: parentId };
  return useQuery({
    queryKey: parentId
      ? [...workItemKeys.list(projectId), "feature", parentId]
      : workItemKeys.list(projectId),
    queryFn: () => listWorkItems(projectId, filters),
    enabled,
  });
}
```

- [ ] **Step 3: Verify existing board tests still pass**

Run: `cd ui && pnpm vitest run src/modules/board/Board.test.tsx src/modules/board/useSetStatus.test.tsx`
Expected: PASS (unchanged behavior — `items` is undefined in those tests).

- [ ] **Step 4: Commit**

```bash
git add ui/src/modules/board/Board.tsx ui/src/modules/board/useBoardItems.ts
git commit -m "feat: Board can render an explicit items list"
```

---

## Task 10: BoardPage epic selection + band wiring

**Files:**
- Modify: `ui/src/modules/board/BoardPage.tsx`
- Modify: `ui/src/modules/work-items/HierarchyTree.tsx`

- [ ] **Step 1: Add epic selection to the hierarchy tree**

In `ui/src/modules/work-items/HierarchyTree.tsx`, extend the props and make epic titles selectable. Update the props type (lines 8-14):

```tsx
}: {
  projectId: string;
  selectedEpic: string | undefined;
  onSelectEpic: (epicId: string | undefined) => void;
  selectedFeature: string | undefined;
  onSelectFeature: (featureId: string | undefined) => void;
}) {
```

Replace the epic title `<span>` (lines 45-46) with a selectable button:

```tsx
            <button
              className={`text-left font-medium ${selectedEpic === epic.id ? "text-accent underline" : "text-fg hover:text-accent"}`}
              onClick={() => onSelectEpic(epic.id)}
            >
              {epic.title}
            </button>
```

- [ ] **Step 2: Wire selection + band in BoardPage**

Replace `ui/src/modules/board/BoardPage.tsx` with:

```tsx
import { useState } from "react";
import { useParams, useSearchParams, Link } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { ChatRail } from "@/modules/chat/ChatRail";
import { HierarchyTree } from "@/modules/work-items/HierarchyTree";
import { TicketPanel } from "@/modules/work-items/TicketPanel";
import { Board } from "./Board";
import { EpicContextBand } from "./EpicContextBand";
import { useEpicBoard } from "./useEpicBoard";

export default function BoardPage() {
  const { projectId } = useParams();
  const [params, setParams] = useSearchParams();
  const [showChat, setShowChat] = useState(false);
  const selectedEpic = params.get("epic") ?? undefined;
  const selectedFeature = params.get("feature") ?? undefined;
  const epicBoard = useEpicBoard(projectId ?? "", selectedEpic);
  if (!projectId) return null;

  const openItem = (id: string) => {
    params.set("item", id);
    setParams(params);
  };
  const selectEpic = (id: string | undefined) => {
    if (id) params.set("epic", id);
    else params.delete("epic");
    params.delete("feature");
    setParams(params);
  };
  const selectFeature = (id: string | undefined) => {
    if (id) params.set("feature", id);
    else params.delete("feature");
    setParams(params);
  };

  const epicTasks = selectedEpic
    ? selectedFeature
      ? (epicBoard.data?.tasks ?? []).filter((t) => t.parent_id === selectedFeature)
      : epicBoard.data?.tasks ?? []
    : undefined;

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center gap-3 border-b border-line bg-surface px-4 py-3">
        <Link to="/" className="text-sm text-accent hover:underline">← Projects</Link>
        <h1 className="font-semibold text-fg">Board</h1>
        <div className="ml-auto flex items-center gap-2">
          <Button size="sm" variant="secondary" onClick={() => setShowChat((v) => !v)}>
            {showChat ? "Hide chat" : "Team lead"}
          </Button>
        </div>
      </header>
      <div className="flex flex-1 overflow-hidden">
        <HierarchyTree
          projectId={projectId}
          selectedEpic={selectedEpic}
          onSelectEpic={selectEpic}
          selectedFeature={selectedFeature}
          onSelectFeature={selectFeature}
        />
        <div className="flex flex-1 flex-col overflow-hidden">
          {selectedEpic && (
            <EpicContextBand
              projectId={projectId}
              epicId={selectedEpic}
              selectedFeature={selectedFeature}
              onSelectFeature={selectFeature}
              onEditEpic={openItem}
            />
          )}
          <div className="flex-1 overflow-auto">
            <Board projectId={projectId} parentId={selectedFeature} items={epicTasks} onOpen={openItem} />
          </div>
        </div>
        {showChat && <ChatRail projectId={projectId} epicId={selectedEpic} />}
      </div>
      {params.get("item") && (
        <TicketPanel
          projectId={projectId}
          itemId={params.get("item")!}
          onClose={() => { params.delete("item"); setParams(params); }}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 3: Verify lint + existing hierarchy/router tests**

Run: `cd ui && pnpm lint && pnpm vitest run src/modules/work-items/HierarchyTree.test.tsx src/app/router.test.tsx`
Expected: lint clean; tests pass. If `HierarchyTree.test.tsx` constructs the component without the new props, update that test to pass `selectedEpic={undefined}` and `onSelectEpic={() => {}}`.

- [ ] **Step 4: Commit**

```bash
git add ui/src/modules/board/BoardPage.tsx ui/src/modules/work-items/HierarchyTree.tsx ui/src/modules/work-items/HierarchyTree.test.tsx
git commit -m "feat: epic selection drives context band + scoped board"
```

---

## Task 11: Chat rail epic scoping + proposed-edit card

**Files:**
- Modify: `ui/src/modules/chat/useChat.ts`
- Modify: `ui/src/modules/chat/ChatRail.tsx`
- Test: `ui/src/modules/chat/ChatRail.test.tsx` (append a test)

- [ ] **Step 1: Write the failing test**

Append to `ui/src/modules/chat/ChatRail.test.tsx` (extend the imports at the top to include `waitFor` if not already present):

```tsx
test("epic-scoped: shows a proposed epic edit and accepts it", async () => {
  server.use(
    http.get("/api/projects/p1/chat", () =>
      HttpResponse.json({ success: true, data: [], error: null, meta: { total: 0, page_size: 50, page_number: 1 } })),
    http.post("/api/projects/p1/chat", () =>
      HttpResponse.json({ success: true, error: null, data: {
        session_id: "s1", reply: "Refined the epic", created_items: [],
        proposed_epic_update: { body: "new spec", acceptance_criteria: ["works"] } } })),
    http.patch("/api/work-items/e1", () =>
      HttpResponse.json({ success: true, error: null, data: { id: "e1" } })),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ChatRail projectId="p1" epicId="e1" />
    </QueryClientProvider>,
  );
  await userEvent.type(screen.getByPlaceholderText(/message the team lead/i), "cart flow");
  await userEvent.click(screen.getByRole("button", { name: /send/i }));
  await waitFor(() => expect(screen.getByText(/suggested epic spec/i)).toBeInTheDocument());
  await userEvent.click(screen.getByRole("button", { name: /apply/i }));
  await waitFor(() => expect(screen.queryByText(/suggested epic spec/i)).not.toBeInTheDocument());
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && pnpm vitest run src/modules/chat/ChatRail.test.tsx`
Expected: FAIL — `ChatRail` has no `epicId` prop / no "Suggested epic spec" card.

- [ ] **Step 3: Update `useChat`**

Replace `ui/src/modules/chat/useChat.ts`:

```typescript
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { postChat, type EpicSpecEdit } from "@/lib/api/chat";
import { epicKeys } from "@/lib/api/epics";
import { updateWorkItem, workItemKeys } from "@/lib/api/workItems";

export interface Turn {
  role: "user" | "assistant";
  content: string;
}

export function useChat(projectId: string, epicId?: string) {
  const qc = useQueryClient();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [proposedEpicUpdate, setProposedEpicUpdate] = useState<EpicSpecEdit | null>(null);

  const send = useMutation({
    mutationFn: (message: string) => postChat(projectId, message, sessionId, epicId),
    onMutate: (message) =>
      setTurns((t) => [...t, { role: "user", content: message }]),
    onSuccess: (res) => {
      setSessionId(res.session_id);
      setTurns((t) => [...t, { role: "assistant", content: res.reply }]);
      setProposedEpicUpdate(res.proposed_epic_update ?? null);
      qc.invalidateQueries({ queryKey: workItemKeys.list(projectId) });
      if (epicId) qc.invalidateQueries({ queryKey: epicKeys.board(epicId) });
    },
  });

  const acceptEpicUpdate = useMutation({
    mutationFn: () =>
      updateWorkItem(epicId as string, {
        body: proposedEpicUpdate?.body ?? undefined,
        acceptance_criteria: proposedEpicUpdate?.acceptance_criteria ?? undefined,
      }),
    onSuccess: () => {
      setProposedEpicUpdate(null);
      if (epicId) qc.invalidateQueries({ queryKey: epicKeys.board(epicId) });
    },
  });

  const dismissEpicUpdate = () => setProposedEpicUpdate(null);

  return { turns, send, proposedEpicUpdate, acceptEpicUpdate, dismissEpicUpdate };
}
```

- [ ] **Step 4: Update `ChatRail`**

Replace `ui/src/modules/chat/ChatRail.tsx`:

```tsx
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Field";
import { useChat } from "./useChat";

interface ChatRailProps {
  projectId: string;
  epicId?: string;
}

export function ChatRail({ projectId, epicId }: ChatRailProps) {
  const { turns, send, proposedEpicUpdate, acceptEpicUpdate, dismissEpicUpdate } = useChat(
    projectId,
    epicId,
  );
  const [text, setText] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed) return;
    send.mutate(trimmed);
    setText("");
  };

  return (
    <aside className="flex h-full w-80 shrink-0 flex-col border-l border-line bg-panel">
      <h2 className="border-b border-line p-2 text-sm font-semibold text-fg">
        {epicId ? "Team lead — focused on epic" : "Team lead"}
      </h2>
      <div className="flex-1 space-y-2 overflow-y-auto p-2 text-sm">
        {turns.map((t, i) => (
          <div key={i} className={t.role === "user" ? "text-right" : ""}>
            <span
              className={`inline-block rounded-lg px-2 py-1 ${
                t.role === "user" ? "bg-accent text-accent-fg" : "bg-surface text-fg"
              }`}
            >
              {t.content}
            </span>
          </div>
        ))}
        {proposedEpicUpdate && (
          <div className="rounded-md border border-line bg-surface p-2">
            <p className="mb-1 text-xs font-semibold text-fg">Suggested epic spec</p>
            {proposedEpicUpdate.body && (
              <p className="mb-1 text-xs text-muted">{proposedEpicUpdate.body}</p>
            )}
            {proposedEpicUpdate.acceptance_criteria?.length ? (
              <ul className="mb-2 list-disc pl-4 text-xs text-muted">
                {proposedEpicUpdate.acceptance_criteria.map((ac, i) => (
                  <li key={i}>{ac}</li>
                ))}
              </ul>
            ) : null}
            <div className="flex gap-2">
              <Button size="sm" loading={acceptEpicUpdate.isPending} onClick={() => acceptEpicUpdate.mutate()}>
                Apply
              </Button>
              <Button size="sm" variant="ghost" onClick={dismissEpicUpdate}>
                Dismiss
              </Button>
            </div>
          </div>
        )}
      </div>
      <form className="flex gap-1 border-t border-line p-2" onSubmit={handleSubmit}>
        <Input
          placeholder="Message the team lead…"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <Button type="submit" size="sm" loading={send.isPending}>Send</Button>
      </form>
    </aside>
  );
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd ui && pnpm vitest run src/modules/chat/ChatRail.test.tsx`
Expected: PASS (existing test + the new epic-scoped test).

- [ ] **Step 6: Commit**

```bash
git add ui/src/modules/chat/useChat.ts ui/src/modules/chat/ChatRail.tsx ui/src/modules/chat/ChatRail.test.tsx
git commit -m "feat: epic-scoped chat rail with proposed epic-edit card"
```

---

## Task 12: Full UI gate

- [ ] **Step 1: Lint + typecheck**

Run: `cd ui && pnpm lint`
Expected: clean (eslint + `tsc --noEmit`).

- [ ] **Step 2: Full UI test suite**

Run: `cd ui && pnpm vitest run`
Expected: all pass.

- [ ] **Step 3: Production build sanity**

Run: `cd ui && pnpm build`
Expected: build succeeds.

(No commit — gate only.)

---

## Task 13: PR

- [ ] **Step 1: Final backend + UI gates green**

Run: `make coverage && make lint && (cd ui && pnpm lint && pnpm vitest run)`
Expected: all green.

- [ ] **Step 2: Push and open the PR**

```bash
git push -u origin docs/epic-spec-breakdown
gh pr create --title "feat: epic spec & breakdown (context band + scoped lead chat)" \
  --body "Implements docs/specs/2026-06-15-epic-spec-and-breakdown-design.md: epic-board aggregation endpoint, epic-focused refinement chat with lead-proposed epic edits, and a board-integrated epic context band with feature filtering. No schema changes. Test plan: backend make coverage + make lint green; UI pnpm lint + vitest + build green."
```

---

## Self-Review Notes

- **Spec coverage:** epic-board read-model (Task 1) + endpoint (Task 2) → "view this information"; epic-focus + `epic_update` (Tasks 3-5) → "spec out an epic with the lead" + "build out features/tasks"; band + selection + filter (Tasks 8, 10) → layout C + feature filter; proposed-edit card (Task 11) → accept/reject epic edit. Per-card feature tag is explicitly out of scope per the spec.
- **Type consistency:** `EpicBoard`/`FeatureProgress` field names match between `domain/epics.py` and `lib/api/epics.ts`; `proposed_epic_update`/`EpicSpecEdit` match between `routes/chat.py` and `lib/api/chat.ts`; `epic_id` query field is consistent across `PostMessage`, `postChat`, and `useChat`.
- **Session scoping:** epic scope is read from `session.epic_id` (set at session creation from `body.epic_id`), so continuing a session keeps the epic focus even when later messages omit `epic_id`.
