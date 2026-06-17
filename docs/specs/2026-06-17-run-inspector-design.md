# Run inspector — design

**Date:** 2026-06-17
**Status:** approved (brainstormed); implementation plan to follow
**Builds on:** the run-events/usage/audit read endpoints (A3/A5d), the board UI runs slice
(`ui/src/modules/runs/`), and the agent-visibility UI (team roster + `AgentDetailPage` Output tab).

## Context

The board UI today shows a run only as a **status badge + current stage** (plus the memory-proposal
card). The rich per-step narration — the `agent_event` stream the orchestrator records — and the
per-stage cost are **not surfaced anywhere**; the only way to see "what is happening during a run"
is to poll `GET /runs/{id}/events` by hand. This is the Phase C **run inspector** gap.

The backend already exposes everything needed (all owner-scoped, envelope responses):
- `GET /runs/{id}` — the `Run` (status, stage, `cost_usd`, token counts, branch, pr_url).
- `GET /runs/{id}/events` — the full `RunEvent` stream (`stage`, `type`, `message`, `created_at`).
- `GET /runs/{id}/usage` — the run's `usage_records` (per stage/role/model: `cost_usd`, tokens).
- `GET /runs/{id}/audit` — capability grants + per-tool allow/deny decisions (deferred to v1.1).

**No backend changes are required for v1.**

## Goals / non-goals

**Goal:** a dedicated, linkable run inspector that shows the **high-level events of a run** and lets
you **drill into the agent narration** for any stage, plus a per-stage cost breakdown — so a human
can follow and debug a run without polling the API.

**Non-goals (deferred):**
- Tool-audit panel (`/runs/{id}/audit`) — folds in as a v1.1 tab.
- Wave-level grouping within `implement` (v1 groups by stage; waves read chronologically inside).
- Realtime sockets — v1 polls, like the rest of the UI.
- Any backend/endpoint change, log/transcript persistence, or raw-token streaming.
- Duplicating the per-agent message view — the existing `AgentDetailPage` **Output** tab stays the
  home for agent-attributed `Message`s; the inspector **cross-links** to it.

## Design

### Route & entry points
A new full-page route **`/runs/:runId`** (`RunInspectorPage`) registered in `src/app/router.tsx`
alongside the existing top-level pages. Entry points: the ticket slide-over's run row (a "View run"
link) and the board assignee chip / team active-now ring (link to the active run). The page links
back to its ticket.

### The two levels (approach A — stage-grouped collapsible timeline)
`RunEvent.type` splits into two classes (pure helper in the runs slice, not the backend):
- **Milestones (level 1):** `stage_started`, `stage_completed`, `agent_dispatched`,
  `agent_reported`, `monitor_started`, `monitor_verdict`, `gate_opened`, `gate_resolved`,
  `blocked`, `quiescence_reached`, `error`.
- **Narration (level 2):** `agent_event` (the agent's streamed output).

Events are grouped by `stage` and the groups are ordered by the canonical pipeline
(`provision → plan → implement → verify → pr → learn`; any unknown/`null` stage sorts last).
Each **stage group** is a collapsible row showing, in chronological order, its milestone events
(icon + message + relative time) and a per-stage **cost chip**. Expanding a group reveals that
stage's **narration** events in order (the drill-down). `agent_dispatched` milestones deep-link to
the dispatched agent's `AgentDetailPage` Output tab. The active stage is auto-expanded; an `error`
event is rendered prominently (danger styling).

### Header & cost
- **Header:** `RunStatusBadge` (reused), current stage, **run total** `cost_usd` + token totals
  (from `GET /runs/{id}`), branch + PR link when present, and a back-link to the ticket.
- **Cost breakdown:** a compact table from `GET /runs/{id}/usage` grouped by stage (and expandable
  to role/model), with the run total — mirrors the existing `BudgetPage` rollup rendering.

### Live updates
React Query with `refetchInterval` while the run is non-terminal; polling stops once
`run.status ∈ {done, failed, blocked, cancelled}`. Events/usage queries share the run's poll cadence.

## Components & files

UI-only; follows the established slice conventions (`lib/api` typed envelope client + key factories;
`modules/<slice>` components + hooks; primitives from `src/ui/`).

- `ui/src/lib/api/runs.ts` — add `getRun(runId)`, `listRunEvents(runId)`, `getRunUsage(runId)` and
  extend `runKeys` (`detail`, `events`, `usage`). Reuse `apiGet`/`apiGetPage` from `./client`.
- `ui/src/lib/api/types.ts` — add `RunEvent` and `UsageRecord` types (mirror the API shapes).
- `ui/src/modules/runs/useRunInspector.ts` — `useRun`, `useRunEvents`, `useRunUsage` hooks with
  terminal-aware `refetchInterval`.
- `ui/src/modules/runs/runEvents.ts` — pure helpers: `MILESTONE_TYPES`/`isNarration`, `groupByStage`
  (ordered), `costByStage(usage)`. Unit-tested in isolation.
- `ui/src/modules/runs/RunInspectorPage.tsx` — page shell: header + cost breakdown + stage timeline.
- `ui/src/modules/runs/StageGroup.tsx` — one collapsible stage (milestones + cost chip + expandable
  narration).
- `ui/src/modules/runs/RunEventRow.tsx` — a single event row (icon by type, message, relative time,
  optional agent deep-link).
- `ui/src/app/router.tsx` — register `/runs/:runId`.
- Entry-point links from `RunSection.tsx` (ticket) and the team/board active-now affordance.

## Data flow

`RunInspectorPage` reads `:runId` → `useRun` (header + terminal check), `useRunEvents` (→ classify
+ `groupByStage`), `useRunUsage` (→ `costByStage` + total). All three poll on the same cadence until
terminal. Pure helpers do the classification/grouping/cost math so rendering stays declarative.

## States
- **Loading:** `Spinner` while the run query is pending.
- **Empty:** a run with no events yet (just provisioned) shows the header + an `EmptyState`
  ("waiting for the first event…") under the timeline.
- **Error:** a failed query surfaces the envelope error message; an `error`-type RunEvent renders in
  danger styling inline in its stage.
- **Unknown stage:** events with a `null`/unrecognised stage collect under a trailing "Other" group.

## Testing strategy (vitest)
- **Pure helpers (`runEvents.ts`):** classify milestone vs narration; `groupByStage` orders stages
  by the pipeline and buckets events; `costByStage` sums `usage_records` per stage + total. (AAA.)
- **`StageGroup`:** collapsed shows milestones + cost chip and hides narration; expanding reveals
  narration; an `agent_dispatched` row links to the agent route.
- **`RunInspectorPage`:** renders header (status/stage/total cost) and stage groups from mocked
  hooks; empty-events → `EmptyState`; terminal run → no further polling (refetchInterval false).
- Use `pnpm vitest run <path>` (never `pnpm test -- <path>`).

## Implementation plan (PR breakdown)
1. **API + types + helpers** — `runs.ts` fetchers/keys, `types.ts` (`RunEvent`/`UsageRecord`),
   `runEvents.ts` pure helpers + their unit tests.
2. **Inspector page** — `useRunInspector` hooks, `RunEventRow`, `StageGroup`, `RunInspectorPage`,
   the `/runs/:runId` route, and component tests.
3. **Entry points** — "View run" link from `RunSection` and the active-now affordance; small tests.

(Three small UI PRs; no backend work.)

## Open risks / deferred
- **Long runs** — `/runs/{id}/events` returns the full list; fine for v1 (runs are bounded by the
  orchestration guards). If event volume grows, add pagination/virtualisation later.
- **Wave context** — collapsing all `implement` events into one stage group loses wave boundaries;
  acceptable for v1, revisit with explicit wave grouping if it reads poorly.
- **Tool-audit + raw transcript persistence** are explicitly out of v1.
