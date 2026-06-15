# Epic Spec & Breakdown — Design

> Status: design (approved 2026-06-15). Closes gap #4 in
> [project-history.md](../project-history.md): "Project-management UX is thin — no epic
> detail view, no epic→feature breakdown flow." Builds on **A6a refinement chat** and the
> **A2 board UI**.

## Goal

Let a user **spec out an epic with the team lead** and have the lead **break it into features
and tasks**, all viewable on the board. The interaction stays a **single continuous lead chat**
(no new workflow gates); the new surface is a board-integrated **epic context band** and an
**epic-scoped** chat.

No new tables and no migration: epics already carry `body` + `acceptance_criteria`, and
`chat_sessions.epic_id` already exists.

## Decisions

- **Layout (board-integrated, layout C).** Selecting an epic pins a context band above the
  kanban. Minimal new surface; closest to today's board.
- **Board content (tasks-only, option A + feature filter).** The kanban shows the epic's
  **tasks** across status columns. Features are summarized as **filter chips** in the band;
  clicking a chip filters tasks to that feature. Tasks show a "↳ <feature>" tag.
- **One continuous chat, epic-scoped.** When an epic is selected, the existing lead chat rail
  is scoped to it (`epic_id`), focusing the lead on that epic.
- **Lead can author the epic spec.** Beyond proposing child features/tasks, the lead may
  propose an edit to the focused epic's own `body` + `acceptance_criteria`. Because that
  mutates an already-accepted item, it is **never auto-applied** — it is surfaced as an
  accept/reject card. (Child proposals continue to land as `Draft`, which is itself the
  "not yet promoted" state.)

## Architecture

Hexagonal as usual — pure domain logic, thin interactors, no I/O in `domain/`.

### Data flow

```
Tree: click epic ─▶ BoardPage selection (selectedEpicId)
                         │
        ┌────────────────┼─────────────────────────────┐
        ▼                ▼                               ▼
  GET epic-board   ChatRail sends epic_id          TicketPanel (edit
  (band + tasks)   ─▶ POST /chat (epic-scoped)       epic spec on demand)
        │                │
        ▼                ▼
  EpicContextBand   lead reply + child Drafts (auto-created)
  + filtered board  + optional proposed_epic_update ─▶ accept/reject card
                                                          │ accept
                                                          ▼
                                                   PATCH /work-items/{epic}
```

## Components

### Backend

**1. Epic-board read-model (aggregation endpoint).**
`GET /projects/{project_id}/epics/{epic_id}/board` →
```
{ epic: WorkItem,
  features: [ { feature: WorkItem, total: int, done: int } ],
  tasks: [ WorkItem ],
  counts: { total: int, done: int } }
```
- `tasks` = all tasks whose parent is the epic **or** any feature of the epic, merged.
- A **pure domain function** `build_epic_board(epic, features, tasks) -> EpicBoard` does the
  grouping and progress counting (no I/O; fully unit-testable). `done` counts work items in
  status `done`.
- The route assembles inputs via owner-scoped `UnitOfWork` `work_items.list` calls (features
  by `parent_id=epic, kind=feature`; tasks per parent), then calls `build_epic_board`. No new
  repository filter semantics; merge in memory (epic sizes are small).

**2. Epic-scoped refinement focus.** In the chat path, when `epic_id` is present:
- Narrow `RefinementContext.hierarchy` to the epic's subtree (epic + its features + their
  tasks) instead of the whole project, so the lead is focused.
- Add a pure `epic_focus_prompt(epic) -> str` to the system prompt instructing the lead to
  refine *this* epic: propose features under it and tasks under those, and optionally refine
  the epic's own spec.

**3. Lead-authored epic spec edit.**
- Extend the refinement contract: `RefinementOutput` gains
  `epic_update: EpicSpecEdit | None`, where `EpicSpecEdit { body: str | None,
  acceptance_criteria: list[str] | None }`.
- The chat route honors `epic_update` **only when the chat is epic-scoped**. It does **not**
  apply it; it returns it in the response as `proposed_epic_update`. The human accepts
  (→ `PATCH /work-items/{epic_id}`) or dismisses.
- Child proposals keep the existing A6a behavior (auto-created as `Draft`, invalid ones
  collected into `notes`).

### Frontend (board module — minimal new surface)

- **`EpicContextBand.tsx`** — pinned above the kanban when an epic is selected: epic title +
  status chip, overall progress (`done/total`), one-line spec summary (click → existing
  `TicketPanel` for full edit), and feature filter chips (each `n/m`, plus an "All tasks"
  chip to clear the sub-filter). Empty epic → "No features yet — ask the lead to break this
  epic down."
- **`useEpicBoard.ts`** — React Query hook for the aggregation endpoint; supplies band data
  and the task list.
- **Selection state** in `BoardPage`: `selectedEpicId` + `selectedFeatureId`. Clicking an epic
  in the tree sets board context (band appears, board filters to the epic, chat scopes to it);
  a feature chip sets the sub-filter.
- **Chat rail** — sends `epic_id = selectedEpicId`; header reads "Lead — focused on:
  <epic title>"; renders an **accept/reject card** when the response includes
  `proposed_epic_update` (accept → PATCH epic + invalidate epic-board query; reject → dismiss).

Feature association is conveyed by the band's feature filter chips (each shows its task
counts and filters the board). A per-task-card "↳ <feature>" tag is deferred (see Out of scope).

## Error handling

- Epic not found / not owned → HTTP 404 via the `{success,data,error}` envelope.
- Empty epic → band renders the "no features yet" prompt (no error).
- `epic_update` returned by the lead while the chat is **not** epic-scoped → ignored.
- Invalid child proposals → collected into `notes` (existing behavior), surfaced in the reply.

## Testing (TDD, 80% gate)

**Unit / domain**
- `build_epic_board`: grouping + progress counts; tasks parented directly to the epic; empty
  epic; mixed statuses.
- `epic_focus_prompt`: includes the epic title and a breakdown instruction.
- `RefinementOutput`: parses `epic_update`; absent `epic_update` → `None`.

**Integration / API**
- `GET …/epics/{id}/board`: returns the subtree + correct counts; owner scoping (other owner →
  404); epic with no children → empty features/tasks, zero counts.
- Epic-scoped chat: narrows hierarchy; returns `proposed_epic_update` when the lead proposes
  one; ignores it when not epic-scoped.
- Accept path: `PATCH /work-items/{epic}` applies body + acceptance criteria.

**UI / vitest**
- `EpicContextBand`: renders progress + chips; feature chip filters tasks; "All tasks" clears.
- Chat sends `epic_id`; proposed-edit card accept calls PATCH and invalidates the epic board.

## Build order

1. `domain`: `EpicBoard` DTO + `build_epic_board` (+ unit tests).
2. API: epic-board aggregation endpoint (+ integration tests).
3. Refinement: epic-scoped hierarchy narrowing, `epic_focus_prompt`, `RefinementOutput.
   epic_update`, chat-route surfacing of `proposed_epic_update` (+ tests).
4. UI: `useEpicBoard` + `EpicContextBand` + `BoardPage` selection state.
5. UI: chat `epic_id` scoping + proposed-edit accept/reject card + task feature tags.

## Out of scope (YAGNI)

- Persisting proposed epic edits as durable artifacts (like memory proposals) — the ephemeral
  accept/reject card is sufficient; revisit only if an audit trail is needed.
- Feature swimlanes / mixed feature+task cards on the kanban (the rejected board-grouping
  options — we chose tasks-only + feature-filter chips).
- A dedicated epic route/page (the rejected epic-view layout — we chose the board-integrated
  context band).
- Per-task-card "↳ <feature>" tag — the band's feature filter chips already convey association;
  the per-card tag is a cosmetic follow-up that would thread feature labels through
  Board → Column → TaskCard.
- Schema changes — none required.
