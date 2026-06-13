# yaah A6a — Refinement chat (Design)

**Date:** 2026-06-13
**Status:** Approved design, pending implementation plan
**Phase:** A6a (refinement chat; memory is A6b)
**Depends on:** A1–A5 (merged to `main`) — board UI + slide-over + right-rail placeholder (A2), work-items CRUD + hierarchy + status machine, projects/teams, capability model (C1/C2: `AgentDefinition` lead + `model_alias`/`system_prompt`), `ModelProvider` (A5ab).

## 1. Problem & goal

The v1 success criterion starts with *"chat with a team-lead agent to turn an idea into a ticket
on the board."* Today the board has no chat — A2 left a right-rail placeholder. A6a adds a
**refinement chat**: a conversation with the team-lead agent, attached to a project (optionally an
epic), that **drafts epics/features/tasks onto the board live** as you talk. Drafts are created as
`Draft` and never auto-promoted to `Ready` (the human still gates that on the board). Memory /
LEARN-stage curation is A6b.

### A6a success criterion

> In the board's right rail I chat with the team-lead agent about an idea; it replies and the
> epics/features/tasks it proposes appear on the board as `Draft` cards within the conversation —
> hierarchy-valid, owner-scoped, and never `Ready`. With no model key configured, a deterministic
> fake agent drives the same flow and all tests pass offline.

## 2. Scope

### In scope
- **`ChatSession` + `ChatMessage`** entities (owner-scoped) + persistence + API to post a message
  and read history.
- **`RefinementAgent`** port + Anthropic/LiteLLM impl + Fake: turns the conversation + project
  context into a `reply` plus structured **work-item proposals**.
- **Synchronous chat endpoint** that persists messages, calls the agent, and applies proposals as
  `Draft` work items (hierarchy-validated, owner-scoped, never `Ready`).
- **Board right-rail `ChatRail`** UI: message list + input; new Drafts appear live (query refetch).

### Out of scope (later)
- Edit/delete tickets via chat (create-only drafting now).
- SSE streaming / persistent team-lead status chat (poll/refetch now).
- Promoting drafts to `Ready` via chat (human-only on the board).
- **Memory / LEARN curation (A6b).**
- Multi-turn tool use beyond proposing work items (e.g., chat editing run config).

## 3. Decisions log

| Decision | Choice | Rationale |
|---|---|---|
| Turn mechanism | **Synchronous API call** (not Temporal) | Chat is interactive; Temporal/durability is overkill for a turn |
| Agent | **New `RefinementAgent` port** (Anthropic/LiteLLM + Fake) | Conversational structured-output call; NOT the sandboxed `ClaudeCodeRuntime` (that's repo work) |
| Model/persona | the project team's **lead** agent `model_alias` + `system_prompt` | Reuses the capability model; routes via the existing `ModelProvider` |
| Proposals | **auto-applied as `Draft`** work items, hierarchy-validated | Spec §5 "drafts onto the board live; nothing Ready without the user" |
| Op set | **create-only** (epic/feature/task) | Smallest useful slice |
| Offline | **Fake agent default** when no model key | Deterministic, offline-green suite |
| UI | **right-rail `ChatRail`** + board query invalidation | Fills the A2 placeholder; Drafts appear live |

## 4. Architecture

```
src/
  domain/
    models.py            # ChatSession, ChatMessage, ChatRole
    refinement.py        # RefinementOutput, WorkItemProposal; system_prompt(); validate_proposal()
  adapters/
    database/            # ChatSessionRow/ChatMessageRow, repos, uow.chat_sessions/chat_messages, ports
    refinement/
      ports.py           # RefinementAgent Protocol + RefinementContext
      anthropic.py       # AnthropicRefinementAgent (structured output via the model)
      fake.py            # FakeRefinementAgent (canned reply + proposals)
  interactors/api/
    routes/chat.py       # POST /projects/{id}/chat ; GET sessions ; GET /chat/{sid}/messages
    deps.py              # refinement_agent dependency (fake unless key configured)
ui/src/features/chat/    # ChatRail, useChat, api/chat.ts (+ board wiring to invalidate work-items)
```

### Domain
```python
class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"

class ChatSession(BaseModel):
    id: str = new_id; owner_id: str; project_id: str
    epic_id: str | None = None; created_at: datetime = utc_now

class ChatMessage(BaseModel):
    id: str = new_id; owner_id: str; session_id: str
    role: ChatRole; content: str; created_at: datetime = utc_now

# domain/refinement.py (pure)
class WorkItemProposal(BaseModel):
    kind: WorkItemKind; parent_id: str | None = None
    title: str; body: str = ""; acceptance_criteria: list[str] = []

class RefinementOutput(BaseModel):
    reply: str
    proposals: list[WorkItemProposal] = []

def system_prompt(project, lead_system_prompt) -> str: ...      # frames the lead as a board refiner
def validate_proposal(p, *, has_parent_resolver) -> None: ...   # epic no parent; feature/task need a valid parent
```

### RefinementAgent
```python
# adapters/refinement/ports.py
class RefinementContext(BaseModel):
    project_name: str
    history: list[ChatMessage]
    hierarchy: list[WorkItem]     # current epics/features (for parent grounding)
    system_prompt: str

class RefinementAgent(Protocol):
    def respond(self, ctx: RefinementContext) -> RefinementOutput: ...
```
- `AnthropicRefinementAgent(model_provider, model)`: one model call with a structured/tool schema
  forcing `{reply, proposals[]}`. `FakeRefinementAgent`: returns a canned reply + one proposal
  derived from the last user message (deterministic for tests).

### API (synchronous)
`POST /projects/{id}/chat` `{message, session_id?, epic_id?}`:
1. `uow.projects.get(id)` (404/owner-scope). Resolve/create the `ChatSession`.
2. Persist the user `ChatMessage`.
3. Build `RefinementContext` (history + project + current epics/features via `uow.work_items.list`)
   using the lead agent's `system_prompt` (from the project team; fallback to a default).
4. `agent.respond(ctx)` → persist the assistant `ChatMessage(reply)`.
5. For each proposal: `validate_proposal` (resolve `parent_id` via owner-scoped `uow.work_items`),
   then `uow.work_items.create(WorkItem(..., status=DRAFT))`. Invalid proposals are skipped with a
   note appended to the reply (never raise the whole turn).
6. Return `{session_id, reply, created_items: [...]}`. All in one UoW transaction.

`GET /projects/{id}/chat` (sessions, paginated) · `GET /chat/{session_id}/messages` (owner-scoped).
`deps.refinement_agent`: `AnthropicRefinementAgent` when a model key is configured, else
`FakeRefinementAgent`.

### UI
`ui/src/features/chat/`: `useChat(projectId)` (history + `useMutation` post), `ChatRail` (message
list + input), wired into `BoardPage`'s right rail (toggle). On a successful post, invalidate the
board's work-items query so new `Draft` cards render live.

## 5. Error handling
- Agent failure (model error) → assistant message "couldn't process that" + no proposals; turn
  returns 200 (chat stays usable). Real errors logged server-side.
- Invalid/cross-tenant `parent_id` in a proposal → that proposal skipped + noted; others still apply.
- Drafts are always `status=DRAFT`; the chat never sets `Ready` (status machine still governs).

## 6. Testing (80% gate)
- **Domain (pure):** `validate_proposal` (epic-no-parent, feature/task need parent), `system_prompt`.
- **Repos:** chat session/message owner-scoping.
- **Fake agent:** reply + proposal shape.
- **API:** post message → assistant reply persisted + `Draft` work items created (assert `status ==
  draft`, not ready); bad parent skipped; history endpoints owner-scoped; no key → fake path.
- **UI (RTL+MSW):** `ChatRail` send → reply rendered + board work-items query invalidated.
- **Opt-in real:** Anthropic refinement call (skip without key).
- Existing suite green (chat is additive; board unchanged except the rail).

## 7. Risks
- **Structured-output reliability** — the model must return well-formed `{reply, proposals}`; use a
  strict schema/tool and tolerate a missing/empty `proposals` (reply-only turn). Covered by the
  fake + opt-in real test.
- **In-flight worktrees** — chat is mostly new files; the only shared touch is `app.py` router
  include + `BoardPage` rail wiring; trivial rebase if needed.
- **Prompt grounding** — passing current hierarchy keeps `parent_id`s valid; invalid proposals are
  skipped, never fatal.
