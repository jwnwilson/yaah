# Run inspector — design

**Date:** 2026-06-17
**Status:** approved (brainstormed); implementation plan to follow
**Builds on:** the run-events/usage/audit read endpoints (A3/A5c/A5d), the board UI runs slice
(`ui/src/modules/runs/`), and the agent-visibility UI (team roster + `AgentDetailPage` Output tab).

## Context

The board UI today shows a run only as a **status badge + current stage** (plus the memory-proposal
card). The rich per-step narration the orchestrator records, the per-stage cost, and the tool
allow/deny decisions are **not surfaced anywhere**; the only way to see "what is happening during a
run" is to poll the API by hand. This is the Phase C **run inspector** gap.

The backend already exposes everything needed (all owner-scoped, envelope responses):
- `GET /runs/{id}` — the `Run` (status, stage, `cost_usd`, token counts, branch, pr_url).
- `GET /runs/{id}/events` — the full `RunEvent` stream (`stage`, `type`, `message`, `created_at`).
- `GET /runs/{id}/usage` — the run's `usage_records` (per stage/role/model: `cost_usd`, tokens).
- `GET /runs/{id}/audit` — `audit_events`: per-stage capability grants + per-tool allow/deny
  decisions (`stage`, `event_type`, payload, `created_at`).

**No backend changes are required** — neither `RunEvent` nor `audit_event` carries a wave/round id,
so round grouping is derived on the client from chronological position (below).

## Goals / non-goals

**Goal:** a dedicated, linkable run inspector that shows the **high-level events of a run grouped by
orchestration round (wave)**, lets you **drill into the agent narration + tool decisions** for any
round/stage, and shows a per-stage **cost** breakdown — so a human can follow and debug a run without
polling the API.

**Non-goals (deferred):**
- Realtime sockets — v1 polls, like the rest of the UI.
- Persisting raw transcripts / token-level streaming.
- Duplicating the per-agent message view — the existing `AgentDetailPage` **Output** tab stays the
  home for agent-attributed `Message`s; the inspector **cross-links** to it.
- An explicit `RunEvent.wave` column — only if the client-side segmentation proves fragile (see risks).

## Design

### Route & entry points
A new full-page route **`/runs/:runId`** (`RunInspectorPage`) in `src/app/router.tsx`, alongside the
existing top-level pages. Entry points: a "View run" link in the ticket slide-over's run row, and the
board assignee chip / team active-now ring (link to the active run). The page links back to its ticket.

### Round (wave) segmentation — the level-1 structure
The orchestrator loops `lead-plan → dispatch engineers → quiescence → monitor-verify` until the
monitor accepts. Neither `RunEvent` nor `audit_event` records a wave number, but both carry
`created_at`, so the inspector **merges the two timestamped streams and segments them into rounds**:

- **Setup** = the leading run of `provision` events (before the first `plan`).
- **Round N** = one orchestration cycle: events from a `plan`-stage start (the lead (re)planning)
  through that cycle's `verify` `monitor_verdict`. The boundary predicate: a `monitor_verdict` closes
  the current round; the next non-`pr`/`learn` event opens round N+1.
- **Wrap-up** = the trailing `pr` + `learn` events after the final round.

Because every event (milestone **and** narration) and every audit decision is placed by chronological
position, each lands in the correct round even though the raw rows only know their `stage`.

### The two levels (approach A — collapsible timeline, round-grouped)
`RunEvent.type` splits into two classes (pure helper, not the backend):
- **Milestones (level 1):** `stage_started`, `stage_completed`, `agent_dispatched`,
  `agent_reported`, `monitor_started`, `monitor_verdict`, `gate_opened`, `gate_resolved`,
  `blocked`, `quiescence_reached`, `error`.
- **Narration (level 2):** `agent_event` (the agent's streamed output).

Each **round** (Setup / Round N / Wrap-up) is a collapsible group. Collapsed, it shows its milestone
events in order (icon + message + relative time), with its stages labelled (plan → implement →
verify). The **active round is auto-expanded**; an `error` event renders in danger styling.

**Drill-down (level 2):** expanding a round reveals, per stage within it:
1. the **capability grant** for that stage (tools / skills / mcp / model, from the
   `capability_granted` audit event),
2. the **`agent_event` narration** in order, and
3. the **tool decisions** (`tool_allowed` / `tool_denied` with reason) for that stage.

`agent_dispatched` milestones deep-link to the dispatched agent's `AgentDetailPage` Output tab.

### Header & cost
- **Header:** `RunStatusBadge` (reused), current stage, **run total** `cost_usd` + token totals
  (from `GET /runs/{id}`), branch + PR link when present, and a back-link to the ticket.
- **Cost breakdown:** a compact table from `GET /runs/{id}/usage` grouped by **stage** (expandable to
  role/model), with the run total — mirrors the existing `BudgetPage` rollup rendering. (Cost stays
  per-stage, not per-round: `usage_records` carry `stage` but no wave.)

### Live updates
React Query with `refetchInterval` while the run is non-terminal; polling stops once
`run.status ∈ {done, failed, blocked, cancelled}`. The run / events / usage / audit queries share the
run's poll cadence.

## Components & files

UI-only; follows the established slice conventions (`lib/api` typed envelope client + key factories;
`modules/<slice>` components + hooks; primitives from `src/ui/`).

- `ui/src/lib/api/runs.ts` — add `getRun`, `listRunEvents`, `getRunUsage`, `listRunAudit`; extend
  `runKeys` (`detail`, `events`, `usage`, `audit`). Reuse `apiGet`/`apiGetPage` from `./client`.
- `ui/src/lib/api/types.ts` — add `RunEvent`, `UsageRecord`, `AuditEvent` types.
- `ui/src/modules/runs/useRunInspector.ts` — `useRun`, `useRunEvents`, `useRunUsage`, `useRunAudit`
  hooks with terminal-aware `refetchInterval`.
- `ui/src/modules/runs/runTimeline.ts` — pure helpers: `MILESTONE_TYPES`/`isNarration`;
  `segmentRounds(events, audit)` → ordered `Round[]` (Setup / Round N / Wrap-up), each with its
  per-stage `{ grant, narration, decisions, milestones }`; `costByStage(usage)`. Unit-tested.
- `ui/src/modules/runs/RunInspectorPage.tsx` — page shell: header + cost breakdown + round timeline.
- `ui/src/modules/runs/RoundGroup.tsx` — one collapsible round (milestones; expands to per-stage
  grant + narration + tool decisions).
- `ui/src/modules/runs/RunEventRow.tsx` — a single event/decision row (icon by type, message,
  relative time, optional agent deep-link).
- `ui/src/app/router.tsx` — register `/runs/:runId`.
- Entry-point links from `RunSection.tsx` (ticket) and the team/board active-now affordance.

## Data flow

`RunInspectorPage` reads `:runId` → `useRun` (header + terminal check), `useRunEvents` + `useRunAudit`
(→ `segmentRounds` merges + buckets by round/stage), `useRunUsage` (→ `costByStage` + total). All
queries poll on the same cadence until terminal. Pure helpers do classification / segmentation / cost
math so rendering stays declarative.

## States
- **Loading:** `Spinner` while the run query is pending.
- **Empty:** a just-provisioned run with no rounds yet shows the header + Setup segment + an
  `EmptyState` ("waiting for the first round…").
- **Error:** a failed query surfaces the envelope error message; an `error`-type RunEvent renders in
  danger styling inline in its round.
- **Unknown stage / unsegmentable tail:** events that don't fit Setup/Round/Wrap-up collect under a
  trailing "Other" group rather than being dropped.

## Testing strategy (vitest)
- **Pure helpers (`runTimeline.ts`):** classify milestone vs narration; `segmentRounds` splits a
  scripted event+audit stream into Setup / Round 1 / Round 2 / Wrap-up and buckets narration + tool
  decisions + grant into the right round/stage by timestamp; a `monitor_verdict` closes a round; the
  "Other" catch-all. `costByStage` sums `usage_records` per stage + total. (AAA.)
- **`RoundGroup`:** collapsed shows milestones; expanding reveals the stage grant + narration + tool
  decisions; an `agent_dispatched` row links to the agent route; an `error` event uses danger styling.
- **`RunInspectorPage`:** renders header (status/stage/total cost), cost-by-stage table, and round
  groups from mocked hooks; empty → `EmptyState`; terminal run → no further polling.
- Use `pnpm vitest run <path>` (never `pnpm test -- <path>`).

## Implementation plan (PR breakdown)
1. **API + types + helpers** — `runs.ts` fetchers/keys, `types.ts` (`RunEvent`/`UsageRecord`/
   `AuditEvent`), `runTimeline.ts` (`isNarration`, `segmentRounds`, `costByStage`) + their unit tests.
2. **Inspector page** — `useRunInspector` hooks, `RunEventRow`, `RoundGroup`, `RunInspectorPage`, the
   `/runs/:runId` route, cost-by-stage table, and component tests.
3. **Entry points** — "View run" link from `RunSection` and the active-now affordance; small tests.

(Three UI PRs; no backend work.)

## Open risks / deferred
- **Round segmentation is heuristic** — derived from event/audit chronology + the `monitor_verdict`
  boundary. If real runs produce sequences it mis-splits, the fallback is a small backend `wave`
  column on `RunEvent` (the orchestrator already tracks the counter); deferred until the heuristic
  demonstrably fails.
- **Long runs** — `/runs/{id}/events` returns the full list; fine for v1 (orchestration guards bound
  it). Add pagination/virtualisation only if volume grows.
- **Cost is per-stage, not per-round** — `usage_records` lack a wave; per-round cost would need the
  same `wave` backend column. Out of v1.
