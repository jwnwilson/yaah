# A6a — Refinement chat — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A team-lead refinement chat that, as you converse, drafts epics/features/tasks onto the board as `Draft` (never `Ready`), in the board's right rail.

**Architecture:** Owner-scoped `ChatSession`/`ChatMessage` entities; a pure `domain/refinement` (proposals + validation + system prompt); a `RefinementAgent` port (Fake default / Anthropic real, via the existing `ModelProvider`); a synchronous `POST /projects/{id}/chat` that persists messages, calls the agent, and applies proposals as `Draft` work items; a `ChatRail` UI that refetches the board so Drafts appear live.

**Tech Stack:** Python 3.12 · FastAPI · SQLAlchemy · httpx (Anthropic) · React/Vite/TanStack Query/MSW · pytest.

**Spec:** `docs/specs/2026-06-13-a6a-refinement-chat-design.md`

**Precondition:** A1–A5 merged. Mirror: entity checklist (`models.py`/`orm.py`/`repositories.py`/`uow.py`/`ports.py`), route style (`routes/work_items.py`), `ModelProvider` (`adapters/model`), `adapters/forge/github_app.py` httpx `_client_factory` seam, ui feature/MSW patterns (`ui/src/features/*`, `ui/src/test`).

## Conventions
- TDD; backend `uv run pytest <path> -v`; frontend `cd ui && npm test -- <path>`; `rm -rf ui/dist` before the full backend suite; commit per task.
- Default-off: no model key → `FakeRefinementAgent`; chat is additive, existing suite stays green.

## Parallel waves
- **Wave 1 (parallel, disjoint):** PERSIST (T1→T2) ‖ REFINEMENT-PURE (T3) ‖ UI (T6).
- **Wave 2:** AGENT (T4) — needs T1 (`ChatMessage`) + T3 (`RefinementOutput`).
- **Wave 3:** API (T5) — needs T1/T2/T3/T4.
- **Wave 4:** T7 verify + integration PR.

---

## Task T1: Chat domain models  (Lane PERSIST)

**Files:** Modify `src/domain/models.py`; Test `tests/unit/test_models.py`.

- [ ] **Step 1: failing test**
```python
def test_chat_models():
    from domain.models import ChatRole, ChatSession, ChatMessage
    s = ChatSession(owner_id="u", project_id="p")
    m = ChatMessage(owner_id="u", session_id=s.id, role=ChatRole.USER, content="hi")
    assert s.id and m.role == "user" and m.content == "hi" and s.epic_id is None
```

- [ ] **Step 2: red** → ImportError.

- [ ] **Step 3: implement** — add to `src/domain/models.py`:
```python
class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatSession(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    project_id: str
    epic_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class ChatMessage(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    session_id: str
    role: ChatRole
    content: str
    created_at: datetime = Field(default_factory=utc_now)
```

- [ ] **Step 4: green** → PASS.
- [ ] **Step 5: commit**
```bash
git add src/domain/models.py tests/unit/test_models.py
git commit -m "feat: ChatSession/ChatMessage/ChatRole domain models"
```

---

## Task T2: Chat persistence  (Lane PERSIST)

**Files:** Modify `src/adapters/database/orm.py`, `repositories.py`, `uow.py`, `ports.py`; Test `tests/unit/test_repositories.py`.

- [ ] **Step 1: failing test**
```python
def test_chat_repos_owner_scoped():
    from adapters.database.engine import make_engine, make_session_factory
    from adapters.database.orm import Base
    from adapters.database.uow import SqlUnitOfWork
    from domain.models import ChatMessage, ChatRole, ChatSession

    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        s = uow.chat_sessions.create(ChatSession(owner_id="u1", project_id="p1"))
        uow.chat_messages.create(ChatMessage(owner_id="u1", session_id=s.id,
                                             role=ChatRole.USER, content="hi"))
        msgs = uow.chat_messages.list(filters={"session_id": s.id}, order_by="created_at")
    assert msgs.total == 1 and msgs.results[0].content == "hi"
    other = SqlUnitOfWork(factory, required_filters={"owner_id": "u2"})
    with other.transaction():
        assert other.chat_sessions.list(filters={"project_id": "p1"}).total == 0
```

- [ ] **Step 2: red** → AttributeError.

- [ ] **Step 3: implement**

`orm.py` (reuse `String/Text/DateTime/Mapped/mapped_column`):
```python
class ChatSessionRow(Base):
    __tablename__ = "chat_sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    epic_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ChatMessageRow(Base):
    __tablename__ = "chat_messages"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

`repositories.py` (import rows + DTOs):
```python
class ChatSessionRepository(SqlRepository[ChatSession]):
    orm_model = ChatSessionRow
    dto = ChatSession


class ChatMessageRepository(SqlRepository[ChatMessage]):
    orm_model = ChatMessageRow
    dto = ChatMessage
    default_order_by = "created_at"
```

`uow.py`:
```python
    @property
    def chat_sessions(self) -> ChatSessionRepository:
        return ChatSessionRepository(self.session, self._required_filters)

    @property
    def chat_messages(self) -> ChatMessageRepository:
        return ChatMessageRepository(self.session, self._required_filters)
```

`ports.py` (import `ChatMessage, ChatSession`; add to `UnitOfWork`):
```python
    @property
    def chat_sessions(self) -> Repository[ChatSession]: ...
    @property
    def chat_messages(self) -> Repository[ChatMessage]: ...
```

- [ ] **Step 4: green** → PASS.
- [ ] **Step 5: commit**
```bash
git add src/adapters/database/orm.py src/adapters/database/repositories.py src/adapters/database/uow.py src/adapters/database/ports.py tests/unit/test_repositories.py
git commit -m "feat: chat_sessions/chat_messages persistence"
```

---

## Task T3: Pure refinement domain  (Lane REFINEMENT-PURE)

**Files:** Create `src/domain/refinement.py`; Test `tests/unit/test_refinement.py`.

- [ ] **Step 1: failing test**
```python
# tests/unit/test_refinement.py
import pytest

from domain.models import WorkItemKind
from domain.refinement import (
    RefinementOutput, WorkItemProposal, system_prompt, validate_proposal,
)


def test_output_and_proposal_shapes():
    out = RefinementOutput(reply="ok", proposals=[
        WorkItemProposal(kind=WorkItemKind.EPIC, title="Auth")])
    assert out.reply == "ok" and out.proposals[0].title == "Auth"


def test_validate_epic_rejects_parent():
    with pytest.raises(ValueError):
        validate_proposal(WorkItemProposal(kind=WorkItemKind.EPIC, parent_id="x", title="E"),
                          parent_exists=lambda pid: True)


def test_validate_feature_requires_existing_parent():
    with pytest.raises(ValueError):
        validate_proposal(WorkItemProposal(kind=WorkItemKind.FEATURE, title="F"),
                          parent_exists=lambda pid: True)            # no parent_id
    with pytest.raises(ValueError):
        validate_proposal(WorkItemProposal(kind=WorkItemKind.FEATURE, parent_id="missing", title="F"),
                          parent_exists=lambda pid: False)           # parent not found
    validate_proposal(WorkItemProposal(kind=WorkItemKind.FEATURE, parent_id="e1", title="F"),
                      parent_exists=lambda pid: True)                # ok


def test_system_prompt_mentions_project_and_drafts():
    p = system_prompt("Alpha", "You are the lead.")
    assert "Alpha" in p and "draft" in p.lower()
```

- [ ] **Step 2: red** → ModuleNotFound.

- [ ] **Step 3: implement** `src/domain/refinement.py`:
```python
"""Pure refinement policy: proposal shapes, validation, system prompt. No I/O."""

from typing import Callable

from pydantic import BaseModel

from domain.models import WorkItemKind


class WorkItemProposal(BaseModel):
    kind: WorkItemKind
    parent_id: str | None = None
    title: str
    body: str = ""
    acceptance_criteria: list[str] = []


class RefinementOutput(BaseModel):
    reply: str = ""
    proposals: list[WorkItemProposal] = []


def validate_proposal(p: WorkItemProposal, *, parent_exists: Callable[[str], bool]) -> None:
    if p.kind == WorkItemKind.EPIC:
        if p.parent_id:
            raise ValueError("epic cannot have a parent")
        return
    if not p.parent_id:
        raise ValueError(f"{p.kind} requires a parent_id")
    if not parent_exists(p.parent_id):
        raise ValueError(f"parent {p.parent_id} not found")


def system_prompt(project_name: str, lead_system_prompt: str = "") -> str:
    base = (lead_system_prompt + "\n\n") if lead_system_prompt else ""
    return (f"{base}You are the team lead refining work for project '{project_name}'. "
            "Converse with the user and propose epics, features, and tasks to draft onto the "
            "board. Features and tasks must reference an existing parent id. Everything you "
            "propose is created as a Draft for human review — never mark anything ready.")
```

- [ ] **Step 4: green** → PASS.
- [ ] **Step 5: commit**
```bash
git add src/domain/refinement.py tests/unit/test_refinement.py
git commit -m "feat: pure refinement domain (proposals, validation, system prompt)"
```

---

## Task T4: RefinementAgent port + Fake + Anthropic  (Lane AGENT, wave 2)

**Files:** Create `src/adapters/refinement/__init__.py`, `ports.py`, `fake.py`, `anthropic.py`; Test `tests/unit/test_refinement_agent.py`.

> Needs T1 (`ChatMessage`) + T3 (`RefinementOutput`).

- [ ] **Step 1: failing test**
```python
# tests/unit/test_refinement_agent.py
import httpx

from adapters.model.fake import FakeModelProvider
from adapters.refinement.anthropic import AnthropicRefinementAgent
from adapters.refinement.fake import FakeRefinementAgent
from adapters.refinement.ports import RefinementContext
from domain.models import ChatMessage, ChatRole


def _ctx():
    return RefinementContext(project_name="Alpha",
                             history=[ChatMessage(owner_id="u", session_id="s",
                                                  role=ChatRole.USER, content="add login")],
                             hierarchy=[], system_prompt="be the lead")


def test_fake_agent_proposes_from_last_message():
    out = FakeRefinementAgent().respond(_ctx())
    assert out.reply
    assert out.proposals and out.proposals[0].title


def test_anthropic_agent_parses_tool_use(monkeypatch):
    agent = AnthropicRefinementAgent(FakeModelProvider())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": [
            {"type": "tool_use", "name": "propose", "input": {
                "reply": "Here's a plan", "proposals": [
                    {"kind": "epic", "title": "Auth", "body": "", "acceptance_criteria": []}]}}]})

    monkeypatch.setattr(agent, "_client_factory",
                        lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    out = agent.respond(_ctx())
    assert out.reply == "Here's a plan" and out.proposals[0].kind == "epic"
```

- [ ] **Step 2: red** → ModuleNotFound.

- [ ] **Step 3: implement**

`__init__.py` (empty). `ports.py`:
```python
from typing import Protocol

from pydantic import BaseModel

from domain.models import ChatMessage, WorkItem
from domain.refinement import RefinementOutput


class RefinementContext(BaseModel):
    project_name: str
    history: list[ChatMessage] = []
    hierarchy: list[WorkItem] = []
    system_prompt: str = ""


class RefinementAgent(Protocol):
    def respond(self, ctx: RefinementContext) -> RefinementOutput: ...
```

`fake.py`:
```python
from adapters.refinement.ports import RefinementContext
from domain.models import WorkItemKind
from domain.refinement import RefinementOutput, WorkItemProposal


class FakeRefinementAgent:
    """Deterministic: echoes the last user message as one drafted epic."""

    def respond(self, ctx: RefinementContext) -> RefinementOutput:
        last = next((m.content for m in reversed(ctx.history) if m.role == "user"), "work")
        title = last.strip()[:60] or "work"
        return RefinementOutput(
            reply=f"Drafted an epic for: {title}",
            proposals=[WorkItemProposal(kind=WorkItemKind.EPIC, title=title)],
        )
```

`anthropic.py`:
```python
import httpx

from adapters.model.ports import ModelProvider
from adapters.refinement.ports import RefinementContext
from domain.refinement import RefinementOutput

_TOOL = {
    "name": "propose",
    "description": "Reply to the user and propose work items to draft.",
    "input_schema": {
        "type": "object",
        "properties": {
            "reply": {"type": "string"},
            "proposals": {"type": "array", "items": {"type": "object", "properties": {
                "kind": {"type": "string", "enum": ["epic", "feature", "task"]},
                "parent_id": {"type": ["string", "null"]},
                "title": {"type": "string"},
                "body": {"type": "string"},
                "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
            }, "required": ["kind", "title"]}},
        },
        "required": ["reply"],
    },
}


class AnthropicRefinementAgent:
    def __init__(self, model: ModelProvider):
        self._model = model

    def _client_factory(self) -> httpx.Client:  # overridden in tests
        return httpx.Client(timeout=60)

    def _base_url(self) -> str:
        return self._model.agent_env().get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")

    def respond(self, ctx: RefinementContext) -> RefinementOutput:
        env = self._model.agent_env()
        msgs = [{"role": m.role, "content": m.content} for m in ctx.history]
        body = {"model": self._model.model_id(), "max_tokens": 2000,
                "system": ctx.system_prompt, "messages": msgs,
                "tools": [_TOOL], "tool_choice": {"type": "tool", "name": "propose"}}
        with self._client_factory() as c:
            r = c.post(f"{self._base_url()}/v1/messages", json=body, headers={
                "x-api-key": env.get("ANTHROPIC_API_KEY", ""),
                "anthropic-version": "2023-06-01", "content-type": "application/json"})
        if r.status_code >= 300:
            return RefinementOutput(reply="(refinement unavailable)", proposals=[])
        for block in r.json().get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == "propose":
                return RefinementOutput(**block["input"])
        return RefinementOutput(reply="(no proposal)", proposals=[])
```

- [ ] **Step 4: green** → PASS.
- [ ] **Step 5: commit**
```bash
git add src/adapters/refinement tests/unit/test_refinement_agent.py
git commit -m "feat: RefinementAgent port + Fake + Anthropic (tool-use)"
```

---

## Task T5: Chat API  (Lane API, wave 3)

**Files:** Create `src/interactors/api/routes/chat.py`; Modify `src/interactors/api/deps.py`, `src/interactors/api/app.py`; Test `tests/integration/test_chat_api.py`.

> Needs T1/T2/T3/T4.

- [ ] **Step 1: failing test**
```python
# tests/integration/test_chat_api.py
from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def _client():
    return TestClient(create_app(Settings(_env_file=None, database_url="sqlite:///:memory:")))


def _project(c) -> str:
    return c.post("/projects", json={"name": "Alpha", "repo_url": "r"}).json()["data"]["id"]


def test_chat_drafts_a_work_item():
    c = _client()
    pid = _project(c)
    r = c.post(f"/projects/{pid}/chat", json={"message": "build login"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["reply"] and data["session_id"]
    assert len(data["created_items"]) == 1
    item = data["created_items"][0]
    assert item["status"] == "draft" and item["kind"] == "epic"   # never ready
    # the draft is on the board
    items = c.get(f"/projects/{pid}/work-items", params={"kind": "epic"}).json()["data"]
    assert any(i["id"] == item["id"] for i in items)


def test_chat_history_round_trips():
    c = _client()
    pid = _project(c)
    sid = c.post(f"/projects/{pid}/chat", json={"message": "hi"}).json()["data"]["session_id"]
    msgs = c.get(f"/chat/{sid}/messages").json()["data"]
    roles = [m["role"] for m in msgs]
    assert "user" in roles and "assistant" in roles
```

- [ ] **Step 2: red** → 404.

- [ ] **Step 3: implement**

`deps.py`:
```python
def refinement_agent(request: Request):
    settings = request.app.state.settings
    if settings.anthropic_api_key or settings.litellm_base_url:
        from adapters.model.anthropic import AnthropicProvider
        from adapters.refinement.anthropic import AnthropicRefinementAgent
        return AnthropicRefinementAgent(AnthropicProvider(api_key=settings.anthropic_api_key,
                                                          model=settings.agent_model))
    from adapters.refinement.fake import FakeRefinementAgent
    return FakeRefinementAgent()
```

`routes/chat.py`:
```python
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from adapters.database.ports import UnitOfWork
from adapters.refinement.ports import RefinementAgent, RefinementContext
from domain.models import ChatMessage, ChatRole, ChatSession, WorkItem, WorkItemStatus
from domain.refinement import system_prompt, validate_proposal
from interactors.api.deps import get_uow, refinement_agent
from interactors.api.envelope import ok

router = APIRouter(tags=["chat"])


class PostMessage(BaseModel):
    message: str
    session_id: str | None = None
    epic_id: str | None = None


@router.post("/projects/{project_id}/chat")
def post_message(project_id: str, body: PostMessage,
                 uow: UnitOfWork = Depends(get_uow),
                 agent: RefinementAgent = Depends(refinement_agent)) -> dict:
    with uow.transaction():
        project = uow.projects.get(project_id)  # 404/owner-scope
        if body.session_id:
            session = uow.chat_sessions.get(body.session_id)
        else:
            session = uow.chat_sessions.create(ChatSession(
                owner_id=project.owner_id, project_id=project_id, epic_id=body.epic_id))
        uow.chat_messages.create(ChatMessage(owner_id=project.owner_id, session_id=session.id,
                                             role=ChatRole.USER, content=body.message))
        history = uow.chat_messages.list(filters={"session_id": session.id},
                                         order_by="created_at", page_size=100).results
        hierarchy = uow.work_items.list(filters={"project_id": project_id},
                                        page_size=200).results
        ctx = RefinementContext(project_name=project.name, history=history,
                                hierarchy=hierarchy, system_prompt=system_prompt(project.name))
        out = agent.respond(ctx)
        uow.chat_messages.create(ChatMessage(owner_id=project.owner_id, session_id=session.id,
                                             role=ChatRole.ASSISTANT, content=out.reply))
        existing_ids = {w.id for w in hierarchy}
        created = []
        notes = []
        for p in out.proposals:
            try:
                validate_proposal(p, parent_exists=lambda pid: pid in existing_ids
                                  or any(c.id == pid for c in created))
            except ValueError as exc:
                notes.append(str(exc))
                continue
            item = uow.work_items.create(WorkItem(
                project_id=project_id, owner_id=project.owner_id, kind=p.kind,
                parent_id=p.parent_id, title=p.title, body=p.body,
                acceptance_criteria=p.acceptance_criteria, status=WorkItemStatus.DRAFT))
            created.append(item)
        reply = out.reply + (("\n\nSkipped: " + "; ".join(notes)) if notes else "")
    return ok({"session_id": session.id, "reply": reply,
               "created_items": [c.model_dump(mode="json") for c in created]})


@router.get("/projects/{project_id}/chat")
def list_sessions(project_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        uow.projects.get(project_id)
        page = uow.chat_sessions.list(filters={"project_id": project_id}, order_by="-created_at")
    return ok([s.model_dump(mode="json") for s in page.results],
              meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number})


@router.get("/chat/{session_id}/messages")
def list_messages(session_id: str, page_size: int = Query(200, ge=1, le=500),
                  uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        uow.chat_sessions.get(session_id)  # 404/owner-scope
        page = uow.chat_messages.list(filters={"session_id": session_id},
                                      order_by="created_at", page_size=page_size)
    return ok([m.model_dump(mode="json") for m in page.results],
              meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number})
```

`app.py`: `from interactors.api.routes import chat` and `app.include_router(chat.router)`.

- [ ] **Step 4: green** → `uv run pytest tests/integration/test_chat_api.py -v` PASS.
- [ ] **Step 5: commit**
```bash
git add src/interactors/api/routes/chat.py src/interactors/api/deps.py src/interactors/api/app.py tests/integration/test_chat_api.py
git commit -m "feat: synchronous refinement chat API (drafts work items)"
```

---

## Task T6: ChatRail UI  (Lane UI, wave 1)

**Files:** Create `ui/src/lib/api/chat.ts`, `ui/src/features/chat/useChat.ts`, `ui/src/features/chat/ChatRail.tsx`; Modify `ui/src/features/board/BoardPage.tsx`; Test `ui/src/features/chat/ChatRail.test.tsx`.

> Independent of backend code (MSW mocks the documented contract).

- [ ] **Step 1: failing test**
```tsx
// ui/src/features/chat/ChatRail.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { ChatRail } from "./ChatRail";

function renderRail() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ChatRail projectId="p1" />
    </QueryClientProvider>,
  );
}

test("sends a message and shows the assistant reply", async () => {
  server.use(
    http.get("/api/projects/p1/chat", () =>
      HttpResponse.json({ success: true, data: [], error: null, meta: { total: 0, page_size: 50, page_number: 1 } })),
    http.post("/api/projects/p1/chat", () =>
      HttpResponse.json({ success: true, error: null, data: {
        session_id: "s1", reply: "Drafted an epic", created_items: [] } })),
  );
  renderRail();
  await userEvent.type(screen.getByPlaceholderText(/message the team lead/i), "build login");
  await userEvent.click(screen.getByRole("button", { name: /send/i }));
  await waitFor(() => expect(screen.getByText("Drafted an epic")).toBeInTheDocument());
});
```

- [ ] **Step 2: red** → module missing.

- [ ] **Step 3: implement**

`ui/src/lib/api/chat.ts`:
```typescript
import { apiGetPage, apiPost } from "./client";

export interface ChatTurn { session_id: string; reply: string; created_items: unknown[] }
export interface ChatMessage { id: string; role: "user" | "assistant"; content: string }

export const chatKeys = { messages: (sid: string) => ["chat", sid] as const };

export async function postChat(projectId: string, message: string, sessionId?: string): Promise<ChatTurn> {
  return apiPost<ChatTurn>(`/projects/${projectId}/chat`, { message, session_id: sessionId });
}

export async function listMessages(sessionId: string): Promise<ChatMessage[]> {
  const { data } = await apiGetPage<ChatMessage[]>(`/chat/${sessionId}/messages?page_size=200`);
  return data;
}
```

`ui/src/features/chat/useChat.ts`:
```typescript
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { postChat } from "../../lib/api/chat";
import { workItemKeys } from "../../lib/api/workItems";

export interface Turn { role: "user" | "assistant"; content: string }

export function useChat(projectId: string) {
  const qc = useQueryClient();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const send = useMutation({
    mutationFn: (message: string) => postChat(projectId, message, sessionId),
    onMutate: (message) => setTurns((t) => [...t, { role: "user", content: message }]),
    onSuccess: (res) => {
      setSessionId(res.session_id);
      setTurns((t) => [...t, { role: "assistant", content: res.reply }]);
      qc.invalidateQueries({ queryKey: workItemKeys.list(projectId) }); // drafts appear live
    },
  });
  return { turns, send };
}
```

`ui/src/features/chat/ChatRail.tsx`:
```tsx
import { useState } from "react";
import { useChat } from "./useChat";

export function ChatRail({ projectId }: { projectId: string }) {
  const { turns, send } = useChat(projectId);
  const [text, setText] = useState("");
  return (
    <aside className="flex h-full w-80 shrink-0 flex-col border-l">
      <h2 className="border-b p-2 text-sm font-semibold">Team lead</h2>
      <div className="flex-1 space-y-2 overflow-y-auto p-2 text-sm">
        {turns.map((t, i) => (
          <div key={i} className={t.role === "user" ? "text-right" : ""}>
            <span className="inline-block rounded bg-gray-100 px-2 py-1">{t.content}</span>
          </div>
        ))}
      </div>
      <form className="flex gap-1 border-t p-2"
            onSubmit={(e) => { e.preventDefault(); if (text.trim()) { send.mutate(text); setText(""); } }}>
        <input className="flex-1 rounded border p-1 text-sm" placeholder="Message the team lead…"
               value={text} onChange={(e) => setText(e.target.value)} />
        <button type="submit" className="rounded bg-blue-600 px-3 py-1 text-sm text-white"
                disabled={send.isPending}>Send</button>
      </form>
    </aside>
  );
}
```

Wire into `BoardPage.tsx`: a toggle that renders `<ChatRail projectId={projectId} />` on the right
(import it; gate behind a `showChat` boolean toggled by a header button). Keep the board layout
intact (`flex`); the rail sits alongside `Board`.

- [ ] **Step 4: green** → `cd ui && npm test -- src/features/chat/ChatRail.test.tsx && npm run lint`.
- [ ] **Step 5: commit**
```bash
git add ui/src/lib/api/chat.ts ui/src/features/chat ui/src/features/board/BoardPage.tsx
git commit -m "feat: ChatRail refinement UI (drafts appear live)"
```

---

## Task T7: Full verify + integration PR  (Wave 4)

- [ ] **Step 1:** backend `rm -rf ui/dist && uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80` → pass, ≥80%.
- [ ] **Step 2:** `uv run ruff check src tests`; `cd ui && npm test && npm run lint`.
- [ ] **Step 3:** Commit fixes; open the integration PR to `main`.

> Coverage note: `AnthropicRefinementAgent` network line beyond the mocked path may use `# pragma: no cover`; the parse/decision paths are covered.

---

## Self-review (resolved)

- **Spec §4 entities** ↔ T1/T2; **refinement domain** ↔ T3; **agent** ↔ T4; **API** ↔ T5; **UI** ↔ T6. ✅
- **Spec §5 error handling** ↔ agent failure → reply-only (T4 anthropic), invalid proposal skipped + noted (T5), drafts always `DRAFT` (T5). ✅
- **Spec §6 testing** ↔ pure (T3), repos (T2), fake+mocked anthropic (T4), API draft+gated+history (T5), UI send+reply (T6). Existing suite green (chat additive; fake default). ✅
- **Type consistency:** `RefinementOutput`/`WorkItemProposal` (T3) used by agents (T4) + API (T5); `RefinementContext` (T4) built in T5; `uow.chat_sessions/chat_messages` (T2) used in T5; `chatKeys`/`postChat`/`listMessages` (T6). `validate_proposal(p, *, parent_exists=...)` signature consistent T3↔T5. ✅
- **Gated:** chat only ever creates `status=DRAFT`; promotion to `Ready` stays on the board's status machine. ✅
- **Localized:** new files + small `app.py` include + `deps.py` dep + `BoardPage` rail wiring; fake default keeps offline suite green. ✅
```
