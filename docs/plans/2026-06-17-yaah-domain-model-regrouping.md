# Plan: regroup `src/domain` models by domain

**Date:** 2026-06-17
**Type:** refactor (no behaviour change)
**Goal:** Split the monolithic `src/domain/models.py` (397 lines, ~16 model groups) into
per-domain modules so each model lives next to the logic that owns it. Delete
`models.py`. No backward-compat facade — every import site is rewritten to the new home.

## Why

`domain/models.py` is a catch-all: Project, WorkItem, Run, Agent, capabilities, audit,
memory, notifications, messages, usage, and chat models all share one file. Logic for
those concepts already lives in dedicated modules (`notifications.py`, `usage.py`,
`memory.py`, `refinement.py`, the `agent/`, `orchestration/`, `transitions/` packages) but
has to reach back into the shared `models.py`. Co-locating models with their logic gives
high cohesion / low coupling (per CLAUDE.md: many small focused files) and makes the
domain boundaries explicit at every call site.

## Decisions (confirmed)

1. **Clean cut, no facade.** Move models, rewrite all ~99 importing files, delete
   `models.py`. Imports name the real domain.
2. **Flat files co-located with logic** (matches current style), not subpackage folders.
3. **Agent split:** `AgentRole`, `Team`, `AgentDefinition` → `domain/agent/models.py`;
   `teams.py` → `domain/agent/teams.py`; `Skill`, `McpServer`, `Secret` →
   `domain/capabilities.py` (owner-scoped entities, distinct from agent-execution policy).

## Scope check

- `adapters/database/orm.py` does **not** import `domain.models` (ORM tables are separate)
  — no ORM churn.
- 99 files import `domain.models` (49 src, 50 tests). No import cycles in the target
  grouping (dependency graph below is a DAG).
- **`transitions/` gets no model file.** It is logic-only; the status enums it operates on
  (`WorkItemStatus`, `RunStatus`, `RunStage`, `AutonomyLevel`) stay with their entities and
  `transitions/*` imports them from there. (Entities must not depend on the state machine.)

## Target layout

Shared helpers → new `domain/base.py`:
- `new_id`, `utc_now`

New flat files:

| File | Models moved in |
|------|-----------------|
| `domain/base.py` | `new_id`, `utc_now` |
| `domain/projects.py` | `AutonomyLevel`, `Project` |
| `domain/work_items.py` | `WorkItemKind`, `WorkItemStatus`, `WorkItem` |
| `domain/runs.py` | `RunStatus`, `RunStage`, `RunEventType`, `RunEvent`, `Run` |
| `domain/messages.py` | `MessageSenderKind`, `MessageRecipientKind`, `MessageKind`, `Message` |
| `domain/audit.py` | `AuditAction`, `AuditEvent` |
| `domain/capabilities.py` | `Skill`, `McpServer`, `Secret` |
| `domain/agent/models.py` | `AgentRole`, `Team`, `AgentDefinition` |

Folded into existing logic modules (model + its logic in one file):

| File | Models added |
|------|--------------|
| `domain/attachments.py` | `WorkItemAttachment` |
| `domain/notifications.py` | `NotificationCategory`, `NotificationSeverity`, `NotificationSource`, `NotificationAction`, `Notification` |
| `domain/usage.py` | `UsageRecord` |
| `domain/memory.py` | `RoleMemoryEntry`, `MemoryProposalStatus`, `MemoryProposal` |
| `domain/refinement.py` | `ChatRole`, `ChatSession`, `ChatMessage` |

Moves:
- `domain/teams.py` → `domain/agent/teams.py` (imports from `domain/agent/models.py`).

Deleted: `domain/models.py`.

> **Naming caveat:** `domain/capabilities.py` (entities) sits alongside
> `domain/agent/capabilities.py` (execution-policy manifest assembly). Different packages,
> but flag in review; rename to `domain/capability_grants.py` if reviewers find it
> confusing.

## Dependency order (DAG — no cycles)

```
base ──────────────► (everything)
projects        → base
work_items      → base
runs            → base
messages        → base
capabilities    → base
agent/models    → base
audit           → base, runs            (AuditEvent uses RunStage)
attachments     → base
notifications   → base, runs            (Notification ← Run, RunEvent)
memory          → base, agent/models    (RoleMemoryEntry ← AgentRole)
refinement      → base, work_items      (proposals ← WorkItemKind; ChatMessage)
usage           → base, runs, agent/models  (UsageRecord ← RunStage, AgentRole)
epics           → work_items            (already a read-model)
agent/teams     → agent/models
agent/capabilities (policy) → agent/models, capabilities, runs
```

## Execution steps

Each step is a self-contained, test-green increment. TDD note: this is a pure
move/rename, so the existing suite **is** the test — `make coverage` must stay green after
every step. Work in a worktree off `origin/main`, ship as one reviewed PR.

1. **`domain/base.py`** — extract `new_id`, `utc_now`. Re-import them into `models.py`
   temporarily so nothing breaks yet. Run tests.
2. **Create the new entity files** (`projects`, `work_items`, `runs`, `messages`, `audit`,
   `capabilities`, `agent/models`) — move the class definitions out of `models.py` into
   them, importing `new_id`/`utc_now` from `base`. Keep `models.py` re-exporting from the
   new files *for this step only* so the suite stays green between moves.
3. **Fold models into existing logic modules** (`attachments`, `notifications`, `usage`,
   `memory`, `refinement`) — move their model classes in, fix their internal
   `from domain.models import` lines to the new homes.
4. **Move `teams.py` → `agent/teams.py`**; update `domain/agent/__init__.py` if it should
   re-export the team factory, and fix its import to `agent/models`.
5. **Rewrite all import sites.** Replace every `from domain.models import X` with the new
   module. Mechanical; do it as a codemod (map symbol → module) and apply across `src/` and
   `tests/`. Group multi-symbol imports by target module. Update `domain/agent/*`,
   `domain/orchestration/*`, `domain/transitions/*` first, then `adapters/`,
   `interactors/`, then `tests/`.
6. **Delete `domain/models.py`** and remove the temporary re-exports. `grep -rn
   "domain.models" src tests` must return nothing. Run `make coverage` + `make lint`.
7. **Docs:** update the `src/domain/` tree in `CLAUDE.md` and the placement notes in
   `docs/architecture.md` to reflect the new files.

## Symbol → new module map (for the codemod)

```
new_id, utc_now                         -> domain.base
AutonomyLevel, Project                  -> domain.projects
WorkItemKind, WorkItemStatus, WorkItem  -> domain.work_items
WorkItemAttachment                      -> domain.attachments
RunStatus, RunStage, RunEventType,
  RunEvent, Run                         -> domain.runs
MessageSenderKind, MessageRecipientKind,
  MessageKind, Message                  -> domain.messages
AuditAction, AuditEvent                 -> domain.audit
Skill, McpServer, Secret                -> domain.capabilities
AgentRole, Team, AgentDefinition        -> domain.agent.models
Notification*, NotificationAction       -> domain.notifications
UsageRecord                             -> domain.usage
RoleMemoryEntry, MemoryProposal,
  MemoryProposalStatus                  -> domain.memory
ChatRole, ChatSession, ChatMessage      -> domain.refinement
```

## Verification

- `make coverage` green (80% gate) after each step and at the end.
- `make lint` green.
- `grep -rn "domain\.models" src tests` → no matches (proves the cut is complete).
- `uv run python -c "import interactors.api.app"` (or app factory import) to catch any
  circular-import regression at module load.

## Risks & mitigations

- **Import churn (99 files):** mechanical; the symbol→module map above is exhaustive.
  Codemod, then let the test suite catch misses.
- **Hidden cycles:** the DAG above is acyclic by construction; the app-import check in
  Verification catches any accidental back-edge.
- **Concurrent agents in this repo:** use a unique branch/worktree name and verify the
  branch is clean before merge (other processes run here).
- **`capabilities.py` name overlap:** flagged above; rename if review objects.
```
