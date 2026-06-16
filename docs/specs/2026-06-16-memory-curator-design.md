# Project-memory curator (revive) — design

**Date:** 2026-06-16
**Status:** approved (brainstormed); implementation plan to follow
**Builds on:** A6b-1/b-2 project memory
(`docs/specs/2026-06-14-a6b-1-project-memory-loop-design.md`,
`docs/specs/2026-06-14-a6b-2-memory-review-design.md`), and the role-memory work
(`docs/specs/2026-06-16-role-memory-design.md`) which revived the project-memory **read**
pointer.

## Context

A6b shipped the project-memory loop on the old fixed-stage `RunWorkflow`: a **LEARN** stage
dispatched a curator agent to update `CLAUDE.md`/`AGENTS.md`/`docs/adr`, and `capture_memory`
committed those edits to a separate `agent/memory-<run>` branch as a reviewable `MemoryProposal`
(apply local-FF / remote-PR / reject, `full_auto` auto-apply — A6b-2).

**The orchestrator cutover dropped the curator.** `OrchestratorWorkflow` ends a run with
`…verify complete → (PR gate) → open_pr → capture_memory → DONE` — **no agent is dispatched to
curate**, so `capture_memory` always finds an empty diff ("no memory changes"). The
`for_stage(RunStage.LEARN)` prompt still exists but is never used. (The role-memory work revived
the **read** pointer in `agent_step`; this spec revives the **write/curation** half.)

This is a small, self-contained revival: add one curation step in the right place; the entire
A6b-2 capture/review/apply pipeline is reused unchanged.

## Goals / non-goals

**Goal:** at the end of a **successful** run, a curator agent updates project memory
(`CLAUDE.md`/`AGENTS.md`/`docs/adr`) with durable learnings, captured via the existing
`capture_memory` → `MemoryProposal` → apply/reject flow — without polluting the work PR.

**Non-goals (deferred):**
- Changes to the A6b-2 capture/review/apply machinery (reused as-is).
- Lead-decided curation (a `curate` intent) — curation is a fixed end-of-run step on the success
  path, matching the old LEARN stage.
- Role memory (DB-backed; separate, already shipped) and Episodic (`progress.md`) memory.
- Curation on blocked/failed/cancelled runs (no completed work to learn from).

## Locked decisions (from brainstorming)

1. **Ordering: `open_pr → CURATE → capture_memory`** (curate *after* the work PR). Curating
   before `open_pr` would let `open_pr`'s `commit_all` sweep the `CLAUDE.md` edits into the *work*
   PR, mixing memory into the code change. After `open_pr`, the work is already committed; the
   curator's edits are then captured *only* onto the separate `agent/memory-<run>` branch.
2. **Generic curator (no agent manifest)** — run with `role=None` so it gets the LEARN stage's
   `Read/Edit/Write` tools (the lead's manifest grants only `Read/Write` — no `Edit` for surgical
   `CLAUDE.md` changes), using the existing `for_stage(LEARN)` prompt enriched with the run's task
   context. No team/role changes.

## Design

### 1. `curate_memory` activity

A new activity (`interactors/temporal/activities.py`) that runs the LEARN-stage agent in the
**main run worktree** to update project memory:
- Resolves the workspace as `runs/{run_id}` (the main worktree, on the task branch) — the same
  place `capture_memory` diffs.
- Runs the agent via `_run_instructed_agent(payload, role=None, instructions="",
  stage=RunStage.LEARN)`. With `role=None` there is no manifest, so `build_invocation` uses the
  LEARN stage's default tools (`Read/Edit/Write`); with empty `instructions` it uses the
  `for_stage(LEARN)` prompt (the existing "update project memory with durable learnings…"
  guidance).
- Best-effort: wraps the run so an agent failure never fails the run — a failed/empty curation
  just yields no memory diff (`capture_memory` then records "no memory changes", as today).
- Registered in `interactors/temporal/worker.py`'s activity list.

### 2. `for_stage(LEARN)` carries the run's task context

`for_stage(RunStage.LEARN, task_title, acceptance_criteria, body)` currently returns a generic
prompt ignoring the task args. Enrich it so the curator knows *what this run did* (ticket title +
acceptance), e.g. append: *"This run completed the ticket: `<title>`. Acceptance:\n`<criteria>`.
Record only durable, project-wide learnings (conventions, gotchas, decisions) — not this task's
specifics."* Pure change in `domain/agent/prompts.py`; keeps the curation prompt centralized.

### 3. `OrchestratorWorkflow`: insert CURATE after `open_pr`

In the success path (after the loop breaks on monitor-complete and the optional PR gate), insert
`curate_memory` **between** `open_pr` and `capture_memory`:

```
await execute_activity("open_pr", {...})          # work committed/PR'd, no memory edits
await execute_activity("curate_memory",           # NEW: curator edits CLAUDE.md/docs/adr
    {"run_id", "owner_id", "task_title", "acceptance_criteria", "body"})
await execute_activity("capture_memory", {...})   # captures memory paths -> MemoryProposal
```

`curate_memory` carries only the run's task context (title/acceptance/body) — with `role=None`
there's no manifest to select, so no `team_id` is needed. Blocked/failed/cancelled runs return
before `open_pr`, so curation never runs on them.

### 4. Reuse, unchanged

`capture_memory` (diff `MEMORY_PATHS` → commit to `agent/memory-<run>` → `MemoryProposal`), the
board's `MemoryProposalCard`, apply (local-FF / remote-PR) / reject, and `full_auto` auto-apply
all work as-is — they finally have edits to capture.

### 5. Error handling

- **Curation agent fails / produces nothing:** best-effort; the run still reaches DONE, and
  `capture_memory` records "no memory changes" (unchanged behavior). Curation never blocks a run.
- **Curator edits outside `MEMORY_PATHS`:** `capture_memory` already diffs only `MEMORY_PATHS`, so
  stray edits are ignored (existing blast-radius guard). The curator runs after `open_pr`, so even
  a stray edit can't reach the work PR.
- **Token/time cost:** one extra agent turn per successful run (matches the old LEARN stage); the
  curator commonly finds nothing durable and exits cheaply.

## Testing strategy

- **Domain (pure):** `for_stage(RunStage.LEARN, …)` includes the project-memory guidance, the
  `Read/Edit/Write` tools, AND the run's task title/acceptance.
- **Activity:** `curate_memory` runs the LEARN agent in the **main** worktree — a capturing fake
  runtime asserts `ctx.stage == LEARN`, `ctx.workspace_path` ends with `runs/{run_id}` (not an
  engineer instance worktree), and the invocation's tools are `Read/Edit/Write`; an agent failure
  is swallowed (activity returns ok, run not failed).
- **Workflow (fake e2e, Temporal test env):** a run whose curator (scripted fake) edits a memory
  file → `capture_memory` produces a **non-empty** `MemoryProposal` (proving the
  `open_pr → curate → capture` wiring); a no-op curator → "no memory changes" (unchanged); a
  blocked run never invokes `curate_memory`.
- **Integration (real git) — no-leakage proof:** with `LocalGit`, run `open_pr` (commit work),
  then a curator-style memory edit, then `capture_memory`; assert the **work branch** does NOT
  contain the `CLAUDE.md` change while the **`agent/memory-<run>` branch** does — pinning decision
  #1 (curate-after-PR keeps memory out of the work PR).

## Implementation plan (PR breakdown)

1. **Curator prompt + activity** — enrich `for_stage(LEARN)` with task context; add the
   `curate_memory` activity (LEARN agent in the main worktree, best-effort) + worker registration;
   domain + activity tests.
2. **Wire into the orchestrator** — insert `curate_memory` between `open_pr` and `capture_memory`
   on the success path; fake-e2e workflow test (curator edit → proposal; no-op → no changes) + the
   real-git no-leakage integration test.

(Two small PRs; the capture/review/apply side needs no changes.)

## Open risks

- **Curation noise:** an over-eager curator could churn `CLAUDE.md` every run. Mitigations: the
  prompt stresses "durable, project-wide only," and **every** edit still goes through the A6b-2
  human review (apply/reject) before landing — nothing auto-lands except under `full_auto` (a
  deliberate, owner-chosen mode). A future "only propose if meaningfully changed" guard can tighten
  it if needed.
- **Per-run cost:** one extra agent turn on every successful run. Acceptable (it matches the prior
  LEARN stage); a later option could skip curation for trivial tickets.
