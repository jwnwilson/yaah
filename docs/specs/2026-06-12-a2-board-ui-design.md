# yaah A2 — Board UI (Design)

**Date:** 2026-06-12
**Status:** Approved design, pending implementation plan
**Phase:** A2 (board UI)
**Depends on:** A1 control-plane foundation (done) and **A1.5 hexrepo refactor (must land first)** —
this UI is designed against the post-A1.5 API contract.

## 1. Problem & goal

A1 gave yaah a working control-plane API (projects, work-items, teams, runs) but no human
interface. The board is the primary human–agent surface (design spec §5). A2 delivers the
**board spine**: a kanban-first React UI where a user creates a project, plans tasks on a
board, and starts a run — proving the visual loop before live execution (A3+) exists.

### A2 success criterion

> Open the app, create a project pointing at a repo, add an epic → feature → task, drag the
> task across the board, open its slide-over panel to edit acceptance criteria, hit **Run**,
> and see a pending run appear in the ticket's run history — all against the real API with the
> 80% coverage gate green.

## 2. Scope

### In scope
- **Projects**: list, create (repo_url or local_path), select/switch.
- **Kanban board** of tasks for the selected project.
- **Slide-over ticket panel**: view/edit title, body, acceptance criteria; change status;
  view run history; **Run** button (creates a pending run).
- **Epic/feature/task CRUD** via a hierarchy tree, and **epic/feature filtering** of the board.
- **Drag-and-drop** status transitions with optimistic update + rollback on rejection.

### Out of scope (deferred — backends do not exist yet)
- Live SSE agent logs, per-agent cost streaming (A3+).
- Team-lead chat rail / refinement chat (A6).
- Actual run execution / Temporal pipeline (A3) — A2 only *creates* a pending run.
- Roadmap view, spend dashboard, Teams / Capabilities / Secrets / Runs-cross-project screens
  (Phase C).
- Multi-user UI; A2 runs under the `dev` auth bypass (`dev-user`).

## 3. Decisions log

| Decision | Choice | Rationale |
|---|---|---|
| Architecture | **Server-state-centric SPA** — TanStack Query is the single source of truth | Lightest fit for REST CRUD; no client/server state drift; optimistic DnD maps to Query mutations |
| Sequencing | **After A1.5** | Avoids building against list/pagination/error shapes that A1.5 changes |
| Stack | React + Vite + Tailwind (repo standard) + **TypeScript strict, TanStack Query, React Router, shadcn-style components, dnd-kit** | Modern, battle-tested defaults; copy-in components keep deps light |
| Column model | **7 flow columns + one "Attention" column** (blocked/failed pool, status chip) | Happy path reads left-to-right; previews the spec's attention-inbox idea; avoids a 9-wide board |
| Cards | **Tasks only** on the board; epics/features are filters + a hierarchy tree | Matches spec: board holds executable units |
| DnD semantics | **Allow any state-machine-valid transition**; invalid drops snap back (API 409) | No agent exists in A2 to drive system transitions; matches `transitions.py` contract exactly |
| Wire isolation | **`lib/api` is the only module that knows the envelope/pagination shapes** | Absorbs A1.5 changes; rest of app consumes plain typed DTOs |
| Testing | vitest + RTL + MSW (unit/integration), Playwright (one E2E happy path), 80% gate | Mirrors backend testing standard |

## 4. Architecture

```
ui/
  src/
    lib/api/         # the ONLY module that knows the wire format
      client.ts        # fetch wrapper: envelope unwrap, error → typed ApiError
      types.ts         # DTOs mirroring domain models (Project, WorkItem, Run, enums)
      projects.ts      # endpoint fns + query/mutation keys
      workItems.ts
      runs.ts
    features/
      projects/      # ProjectList, CreateProjectDialog, project switcher
      board/         # Board, Column, TaskCard, useBoardDnd, FilterBar
      work-items/    # TicketPanel (slide-over), edit forms, AcceptanceCriteria editor,
                     # HierarchyTree (epic/feature/task CRUD)
      runs/          # RunList, RunStatusBadge (inside the ticket panel)
    components/ui/   # shadcn-style primitives (Button, Dialog, Badge, Sheet, Toast…)
    app/             # router, QueryClient provider, layout shell, error boundary
    main.tsx
  index.html
  vite.config.ts     # dev proxy /api → uvicorn :8000
  tailwind.config.ts
  tsconfig.json      # strict
  package.json
```

**Routing** (React Router): `/` = projects; `/projects/:id` = board. Panel and filter state
live in the URL query (`?epic=&feature=&item=`) so views are shareable and survive refresh.

**State**: TanStack Query holds all server state. No separate client store of board data.
Query keys are namespaced per resource in `lib/api/*`. Mutations invalidate the relevant
queries; DnD uses optimistic updates with snapshot rollback.

## 5. Components & data flow

### Projects
- **ProjectList** — `GET /projects` (paginated). Empty state prompts creation.
- **CreateProjectDialog** — `POST /projects`. Client-side validation mirrors the domain
  rule (must have `repo_url` **or** `local_path`); server 422 surfaces inline.
- **Project switcher** — navigates to `/projects/:id`.

### Board
- Fetches tasks via `GET /projects/:id/work-items` filtered to `kind=task` (+ optional
  `parent_id` for feature filter), using the post-A1.5 `filters` JSON param and pagination.
- Groups tasks into **7 flow columns** (Draft, Refining, Ready, In Progress, In Review,
  Approved, Done) **+ Attention** (blocked + failed, each card showing a red status chip).
- **FilterBar** — cascading epic → feature selects scope the board; selection reflected in URL.
- **DnD (dnd-kit)** — dropping a card onto a column calls `POST /work-items/:id/status`
  optimistically. On 409 (`InvalidTransition`) or 404 the card snaps back and a toast
  explains. The set of legal target columns is shown as a display hint derived from the
  status machine; the server remains the authority.

### Ticket panel (slide-over `Sheet`)
- Opens from a card (`?item=<id>`). Sections:
  - **Details** — title, body (markdown textarea), status control.
  - **Acceptance criteria** — add/edit/remove list items → `PATCH /work-items/:id`.
  - **Runs** — `GET /work-items/:id/runs`; each run shows status badge, stage, created time
    (read-only in A2). **Run** button → `POST /work-items/:id/runs` creates a pending run and
    refreshes the list.

### Hierarchy tree
- Sidebar of epics → features → tasks for the project. Create/rename/delete any kind
  (work-items CRUD supports all kinds). Creating a feature/task seeds `parent_id`; client
  mirrors the domain hierarchy rules (epics have no parent; feature/task require a parent)
  with server validation as the authority.

## 6. Error handling

- `lib/api/client.ts` unwraps `{success, data, error}`; non-success throws a typed
  `ApiError{status, message}`. Errors are never silently swallowed.
- Query (read) errors render inline with a retry affordance; mutation errors raise toasts.
- Optimistic DnD mutations roll back via Query `onMutate` snapshot + `onError` restore.
- A top-level **error boundary** catches render crashes with a friendly fallback.
- 422 field errors map back to the originating form input where the API provides field context.
- HTTP→meaning mapping consumed by the UI (set server-side by A1.5): 404 not-found,
  409 invalid transition / integrity conflict, 422 validation.

## 7. Testing (80% coverage gate)

- **Unit (vitest + React Testing Library):** column-grouping logic, optimistic-update/rollback
  behavior, API client envelope-unwrap + error mapping, form validators.
- **Integration (RTL + MSW):** create-project, edit-ticket, drag-to-transition (success **and**
  409 rollback), start-run — against mocked realistic envelope responses.
- **E2E (Playwright):** one happy path — create project → create task → drag through columns →
  open panel → hit Run → see pending run — against the running app with a seeded backend.

## 8. Build & dev integration

- Vite dev server proxies `/api` → uvicorn (`:8000`); `npm run build` emits `ui/dist`, served
  by FastAPI as static assets in both compose profiles.
- Makefile targets: `make ui` (dev), `make ui-build`, `make ui-test`; the UI coverage gate
  joins the existing CI gates.

## 9. Risks & dependencies

- **Hard dependency on A1.5** for final list/pagination/error shapes. If A2 must start before
  A1.5 merges, only `lib/api` changes when it lands — the rest of the app is insulated.
- dnd-kit + optimistic Query updates need careful cache-key discipline; covered by integration
  tests for the rollback path.
- Markdown rendering of bodies is plain textarea in A2; rich rendering deferred.
