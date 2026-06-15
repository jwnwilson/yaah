# Parallel same-role engineers — design

**Date:** 2026-06-15
**Status:** approved (brainstormed); implementation plan to follow
**Builds on:** [ADR-0002 lead-driven orchestration](../adr/0002-lead-driven-orchestration.md);
the orchestrator cutover (PR #109) which made `OrchestratorWorkflow` the sole run path.

## Context

The orchestrator runs a ticket as a lead-driven loop: `invoke_lead → (dispatch | verify |
block | gate) → … → PR → LEARN`. Today the lead's `continue` decision dispatches **one
`AgentWorkflow` child per role per wave** (`id=agent-{run}-{role}`), signals
`deliver → stop_now`, and `asyncio.gather`s it to completion. All agents (lead, engineer, QA)
**share one git worktree** at `runs/{run_id}` on `agent/<task>`.

The cutover deliberately deferred four things to this spec: **multiple same-role workers, true
concurrent waves, quiescence/settle-window detection, and live agent-to-agent messaging.**

## Goals / non-goals

**Goal:** let the lead dispatch **N engineers of the same role** to work one ticket
**concurrently and in isolation**, then integrate their work back into the task branch — so a
parallelizable ticket finishes faster, matching the "virtual dev team" vision.

**Non-goals (deferred):**
- **Live engineer↔engineer messaging.** Isolated worktrees remove the clobbering that would
  require it; coordination stays lead-mediated. The peer-routing plumbing in `AgentWorkflow`
  stays dormant, ready for a future need.
- **A persistent actor pool** with continuous quiescence polling (the `is_quiescent` /
  settle-window machinery). Not needed for the wave-based model below.
- AI-assisted conflict resolution (a merge agent). Conflicts are a deterministic re-plan.

## Locked decisions (from brainstorming)

1. **Workspace model — isolated worktrees + merge.** Each engineer edits its own worktree/
   branch; an integration step merges them back. No clobbering; true parallelism.
2. **Merge strategy — deterministic git merge; conflict → lead re-plans.** No AI in the merge.
   A conflict is reported to the lead, which re-dispatches the conflicting engineer (or blocks).
3. **Coordination — lead-mediated.** The lead writes N briefs, collects reports, triggers
   integration, and re-plans on conflict. No peer messaging.

## Design

### 1. Execution model — N concurrent actors per wave

A small generalization of the existing loop, not a rewrite. A role appearing **K times** in
`decision.dispatches` spawns **K instanced actors**, each `deliver`'d its own brief +
`stop_now`, then a single `asyncio.gather(...)` over all K. Temporal runs them genuinely
concurrently; **`gather` completing is the quiescence barrier** — because each actor drains one
brief and exits, no settle-window detection is needed.

- Actor identity becomes per-instance: `id=agent-{run}-{role}-{wave}-{i}` (today:
  `agent-{run}-{role}`). This also fixes the latent same-role id collision noted in the cutover.
- `AgentWorkflow` is otherwise unchanged (durable drain loop; returns `{role, processed,
  outcome, cost_usd}`). It gains an instance-specific **workspace key** and **branch** in its
  input.
- **N=1 is the same code path** — a wave of one actor whose branch integrates into
  `agent/<task>` as a trivial fast-forward. The single-engineer run reaches the same observable
  outcome as today (done + a committed `agent/<task>`); parity is *by outcome*, not by internal
  mechanism (the engineer now works in an instance worktree and the commit moves from `open_pr`
  to per-branch + integrate — see §3). This keeps one unified path instead of special-casing N=1.

### 2. Workspace & branches — per-engineer isolation

- **Main worktree** (unchanged): `runs/{run_id}` on `agent/<task>`. Used by `invoke_lead`,
  `run_monitor`, and as the **integration target**.
- **Per-engineer worktree**: `runs/{run_id}/w/{role}-{wave}-{i}` on branch
  `agent/<task>__{role}-{wave}-{i}`, cut off `agent/<task>`.
- New **`provision_engineer_workspace`** activity creates each per-engineer worktree off the
  current task branch (so a re-dispatch after a partial integration branches off the *integrated*
  state).
- **`agent_step` / `_run_instructed_agent` gains a `workspace_key`** (today it hardcodes
  `runs/{run_id}`). Lead/monitor pass the main key; engineers pass their instance key. The pure
  `build_invocation`/`RunContext` already take the workspace path — only the activity wiring
  changes.
- Cleanup: each engineer worktree is removed after integration; all run worktrees are reclaimed
  on terminal states (extends the existing `cleanup_workspace`).

### 3. Commit, integration & conflict → re-plan

**Commit each engineer's work to its branch first.** After `gather`, each engineer worktree
holds uncommitted edits on its own branch. The parent commits each via the existing
`commit_all(engineer_worktree, msg, exclude=WORKSPACE_SCRATCH)` (the scratch-exclusion from
PR #109 — so `.claude/`/`.orchestration/` stay out). An engineer that produced no changes
contributes no branch and is skipped. This is the only place engineer work is committed; the
final `open_pr` no longer commits (see below).

**Then integrate.** New **`integrate_branches`** activity merges each committed engineer branch
into `agent/<task>` in the main worktree, in a deterministic order from a pure
`integration_plan(reports)` helper (default: dispatch order). Returns `{merged: [branch…],
conflict: {branch, files} | None}`. Uses `git merge`; on the first conflict it **aborts the
merge** (`git merge --abort`) and returns the conflict — never leaving the worktree conflicted.
A new **`GitPort.merge_branch(workspace, *, branch) -> MergeResult`** (fast-forward or real merge,
conflict surfaced — adjacent to the existing `merge_into_base`).

**`open_pr` opens the PR for the already-integrated branch.** Because integration committed the
work, the main worktree is clean at PR time, so the current "`commit_all` found nothing → no PR"
logic would wrongly skip the PR. `open_pr` changes to proceed when `agent/<task>` has commits
**ahead of base** (new `GitPort.has_commits_ahead(workspace, base)`), independent of working-tree
changes — then push + open PR / record the branch as today.

- Parent flow after a wave's `gather`:
  - **Clean integration** → record each engineer's `AgentReport` into state → loop (lead is
    re-invoked; with work merged it will typically choose `verify`).
  - **Conflict** → record `OrchestrationState.last_integration` (conflicting branch + files) →
    loop. The lead sees the conflict in its prompt and re-dispatches the conflicting engineer
    with a "resolve against the integrated base" brief; that engineer provisions a **fresh
    worktree off the now-partially-integrated `agent/<task>`** and redoes its piece → re-integrate.
  - Bounded by a new **`max_integration_rounds`** guard → else `block`, surfacing the conflicting
    files in the blocked event.

### 4. Domain & guards

- `Dispatch` already carries `target_role` + `instructions`; **K same-role dispatches = K
  engineers** — no schema change required. (Optional: an `instance_label` for nicer UI/audit.)
- **`OrchestrationLimits.max_parallel_per_role`** (new) caps K per wave; `guard_exceeded`
  rejects a wave that exceeds it (forces `block`). `max_integration_rounds` (new) bounds the
  conflict re-plan loop. Existing guards (`max_waves/dispatches/messages/cost`) still apply.
- **`OrchestrationState.last_integration`** (new, nullable): the most recent integration result,
  serialized into the orchestrator prompt so the lead can react to conflicts.
- The orchestrator prompt (`build_orchestrator_prompt`) gains a short "integration status"
  section when `last_integration` is present.

### 5. Workflow changes (`OrchestratorWorkflow`)

The `continue` branch changes from "dispatch one actor per role" to:
1. group `decision.dispatches` (K instances per role), enforce `max_parallel_per_role`,
2. for each instance: `provision_engineer_workspace` → `start_child_workflow(AgentWorkflow, …,
   id=agent-{run}-{role}-{wave}-{i}, workspace_key, branch)` → `deliver` brief → `stop_now`,
3. `gather` all instances; thread real cost + worst outcome into state (as today),
4. commit each engineer worktree to its branch (`commit_all` + scratch exclusion; skip empties),
5. `integrate_branches`; on conflict set `last_integration` and continue the loop; on clean
   continue the loop,
6. guards checked before each wave (incl. `max_parallel_per_role`, `max_integration_rounds`).

`open_pr` is adjusted to push/open based on commits-ahead-of-base (§3); `run_monitor` runs on the
main worktree, so it verifies the **integrated** result.

`AgentWorkflow`, `invoke_lead`, `run_monitor`, `open_pr`, `capture_memory` are unchanged except
for the workspace-key parameterization and the new integration activity.

### 6. Error handling

- **Engineer step fails** → its `AgentReport.outcome=fail` (today's path) → lead re-plans
  (re-dispatch or block). A failed engineer's branch is simply not integrated.
- **Integration conflict** → bounded re-plan (above) → else block with conflicting files.
- **Crash/resume** → Temporal resumes from the last activity; per-engineer worktrees are
  deterministic by id, so provision is idempotent (re-create if missing).
- **Guard exceeded** → `block` with the guard name (not silent), as today.

## Testing strategy

- **Domain (pure):** `integration_plan(reports)` ordering; `guard_exceeded` for
  `max_parallel_per_role` and `max_integration_rounds`; prompt includes integration status.
- **Activity:** `integrate_branches` against real git — clean multi-branch merge; a real
  conflict returns `conflict` and leaves the worktree un-conflicted (post-`--abort`);
  `provision_engineer_workspace` cuts the branch off the current task branch; `open_pr` opens/
  records the PR when the branch is ahead of base with a clean working tree (no `commit_all`
  changes).
- **Workflow (fake e2e, Temporal test env):**
  - two engineers, disjoint files → clean integrate → verify → done;
  - two engineers, conflicting files → lead re-dispatches the conflicting one → re-integrate →
    done;
  - conflict never resolves → `max_integration_rounds` → blocked;
  - `max_parallel_per_role` exceeded → blocked.
- **Parity:** N=1 single-engineer run reaches done + commits to `agent/<task>` exactly as the
  current orchestrator (guards against regressions in the generalized path).

## Implementation plan (PR breakdown)

1. **Per-engineer worktrees** — `provision_engineer_workspace` activity, `GitPort` support for
   branching off the task branch, parameterize `agent_step`/`_run_instructed_agent` with a
   `workspace_key`. (N still 1; no behavior change yet — pure enabling refactor + tests.)
2. **Instanced concurrent dispatch** — per-instance actor ids, group dispatches by role, spawn
   K concurrent actors per wave, `max_parallel_per_role` guard. (Engineers now run in parallel
   on isolated branches; integration still trivial/manual.)
3. **Integration + conflict re-plan** — commit-engineer-branches step, `integrate_branches`
   activity + `GitPort.merge_branch` + `has_commits_ahead`, `open_pr` ahead-of-base change,
   `OrchestrationState.last_integration`, prompt section, `max_integration_rounds`, the
   conflict→re-plan loop in `OrchestratorWorkflow`.

(A later, optional PR can surface parallel engineers on the board UI — multiple active-now
assignee chips / per-instance output — building on the agent-visibility UI.)

## Open risks

- **Conflict thrash:** if the lead partitions work poorly, engineers conflict repeatedly until
  `max_integration_rounds` blocks. Mitigation: the lead prompt should encourage disjoint briefs
  (by file/area); the guard makes failure legible rather than infinite.
- **Token cost:** K concurrent engineers ≈ K× implement cost per wave; the existing `max_cost`
  guard bounds it, and the lead chooses K per ticket.
- **Worktree disk:** K worktrees per run; reclaimed after integration and on terminal states.
