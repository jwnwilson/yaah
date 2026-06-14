# Agent-Visibility UI — design spec (Spec 2)

**Date**: 2026-06-14
**Status**: approved (brainstorm) — implementation plans to follow
**Builds on**: the lead-orchestration foundation (ADR-0002; PRs #83/#85/#86/#88/#89/#90/#91). This is the observability layer over that backend.

## 1. Goal

Surface the virtual dev team in the UI: see all team agents, click an agent to read its output, read a message inbox (messages to me and to each agent — including the real inter-agent messages the orchestrator now produces), and see which agent a ticket is assigned to (with a small per-agent icon). This is the original request that motivated the whole orchestration build-out; the backend it visualizes now exists.

## 2. Backend additions (this spec)

Most data already has endpoints (`/teams/{id}/agents`, `/runs/{id}/events`, `/runs/{id}/usage`, `/notifications`). New work:

1. **`/messages` router** over the existing owner-scoped `MessageRepository` (Plan 1):
   - `GET /messages?box=me|<agentId>&status=unread|read&page_size=&page_number=` — `box=me` -> `recipient_kind=user`; `box=<agentId>` -> `recipient_agent_id=<id>`. Owner-scoped, so the user can read every agent's mailbox.
   - `GET /messages/unread-count?box=...` -> `{count}`.
   - `PATCH /messages/{id}` `{read: true}` -> sets `read_at`.
   - `POST /messages` -> a user-authored note to an agent (`sender_kind=user`, `recipient_kind=agent`). Minimal; enables an interactive inbox.
   - Envelope + pagination meta like the other routers.
2. **`assignee_agent_id` on `UpdateWorkItem`** — let the user override the assignee via the existing `PATCH /work-items/{id}`.
3. **Orchestrator persists the assignee** — a small `set_assignee` activity called from `OrchestratorWorkflow` when the lead's decision carries `assignee_role` (resolved to an agent id via the team). This is the deferred 3d follow-up; it makes the chip reflect the lead's choice.
4. *(Optional)* `GET /agents/{id}/runs` returning the runs an agent participated in (its role's stages) for the Output view; else the client derives from `/work-items/{id}/runs` + `/runs/{id}/events`. Decide during plan 2b.

## 3. Frontend surfaces (`ui/src/features/`)

Follow the existing feature-folder + react-query + Tailwind conventions (see `features/board`, `features/manage`).

1. **Team page** (`/team`, `features/team/`): roster of the active project's team agents (`GET /teams/{teamId}/agents`). Each card: avatar (role icon + color + initials), name, role, model alias, purpose, an unread-message badge (`/messages/unread-count?box=<agentId>`), and an idle/active status. Click -> agent detail.
2. **Agent detail** (`/team/:agentId`, `features/team/AgentDetail.tsx`): header (avatar, name, role, model, persona/purpose) + two tabs:
   - **Output** — structured stage results: the runs this agent worked, each showing its stage events (plan text, diff/branch, test results), status, and cost/tokens, grouped by run/ticket. Read-only.
   - **Inbox** — this agent's messages (`box=<agentId>`).
3. **Inbox page** (`/inbox`, `features/inbox/`): a mailbox switcher — **Me** plus one entry per agent (each with an unread badge). Selecting a mailbox lists its messages (sender avatar, kind, subject/body, clickable ticket/run context, timestamp, read state). Opening a message marks it read; a compose box sends a note to the selected agent. Top-level **Inbox** nav entry shows the "Me" unread total.
4. **TaskCard assignee chip** (`features/board/TaskCard.tsx`): render the assignee agent's avatar in the card corner (hover -> name/role); a small picker (team agents) writes the override via `PATCH /work-items/{id}`. When a run is active and its current dispatch targets a different agent, overlay a subtle "active now" ring (derived from the run's events).
5. **Navigation** (`app/AppLayout.tsx` + `app/router.tsx`): add **Team** and **Inbox** top-level entries alongside Board/Projects/Manage. The notification bell is unchanged.

## 4. Cross-cutting

- **Agent identity:** a deterministic `roleVisual(role) -> {icon, color}` + name-initials, used everywhere an agent appears (roster, assignee chip, message sender) so identity is consistent. No backend change.
- **Data flow:** react-query queries with polling for `/messages`, `/messages/unread-count`, `/teams/{id}/agents`, `/work-items` (assignee rides the payload), `/runs/{id}/events`. Mutations: mark-read, send message, set assignee.
- **Empty/error states:** agent with no output, empty mailbox, no team assigned -> clear, friendly messages.

## 5. Decomposition (sequential, each shippable)

- **2a — Backend: messages API + assignee.** `/messages` router, `assignee_agent_id` on `UpdateWorkItem`, orchestrator `set_assignee`. (Backend only; unblocks all UI.)
- **2b — Team roster + agent detail/output.** Team page, agent detail with Output + Inbox tabs, the shared agent-identity helper.
- **2c — Inbox page.** Mailbox switcher, message list, mark-read, compose.
- **2d — Assignee chip on the board.** TaskCard avatar + picker + active-now ring.

## 6. Testing

- **Backend:** message endpoints (list by mailbox, unread-count, mark-read, send; owner scoping), `UpdateWorkItem.assignee_agent_id`, the `set_assignee` activity, orchestrator-sets-assignee. pytest + TestClient.
- **Frontend:** vitest + MSW per surface (Team roster render, agent Output grouping, Inbox switcher + mark-read + compose, TaskCard chip + picker). Follow the existing `ui/src/**/*.test.tsx` patterns. Note: run UI tests with `pnpm vitest run <path>` (project convention).

## 7. Scope boundaries (YAGNI)

- No message threading/replies (flat + context links).
- No realtime sockets — react-query polling (SSE is a later enhancement, consistent with the current board).
- Per-agent capability editing stays in **Manage**; the Team page links to it rather than duplicating.
- "Active now" ring is derived from run events, not a new presence system.
