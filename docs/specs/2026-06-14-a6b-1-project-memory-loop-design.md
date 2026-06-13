# A6b-1 — Project Memory Loop (Design)

**Status:** approved
**Date:** 2026-06-14
**Parent:** A6 (memory), see [docs/specs/2026-06-12-yaah-design.md](2026-06-12-yaah-design.md) §6 (LEARN stage), §8 (memory)
**Predecessor:** A6a refinement chat (merged)

## Goal

Close the read → use → learn loop for **project-scoped** memory. Agents read
project memory before they work, and the LEARN-stage curator emits **durable,
reviewable** memory changes that survive workspace cleanup.

Today the loop is broken in two places:

1. **Memory is never read back.** §6 says the lead agent "reads ticket + project
   memory", but no stage prompt references project memory, so it influences nothing.
2. **Curator writes are thrown away.** The LEARN stage writes into the run
   workspace, which `cleanup_workspace` then destroys. Nothing persists.

A6b-1 fixes both for the project scope only.

## Scope

### In scope

- Inject a project-memory pointer into the **PLAN** and **IMPLEMENT** stage prompts.
- Strengthen the **LEARN** curator prompt to update project memory (additions *and*
  deletions), bounded to memory paths.
- Capture the curator's changes to memory paths as a unified diff.
- Persist the diff as a durable `MemoryProposal` (Postgres).
- Commit memory changes to a dedicated `agent/memory-<run_id>` branch and
  **push-and-hold** it (push if a remote/token exists; never auto-merge).
- Surface a run-timeline event and a read-only `GET /runs/{run_id}/memory` endpoint.

### Out of scope (explicit)

- Role memory repo (`roles/<role>.md`) → **A6b-3**.
- In-app memory-diff review/apply UI + auto-apply-in-`full_auto` gating → **A6b-2**.
- Episodic `progress.md` changes (already exists as a workspace artifact).
- pgvector RAG over docs/ADRs (Phase B).

## Memory paths (the bounded set)

A single shared constant defines what counts as "project memory":

```
CLAUDE.md
AGENTS.md
docs/adr/**            (matched as docs/adr/ prefix)
```

The curator may edit anything, but the harness only ever **captures and commits
these paths**. Curator edits outside this set are ignored — this is the structural
blast-radius guard (we do not attempt per-file tool sandboxing).

## Components

### A. Memory injection (read side) — `src/domain/prompts.py`

A shared pointer string is prepended to the PLAN and IMPLEMENT prompts:

> Before you begin, read project memory if present: `CLAUDE.md` or `AGENTS.md` at
> the repo root, and any relevant files under `docs/adr/`. Honor the conventions,
> decisions, and gotchas recorded there.

- PLAN tools already include `Read`; IMPLEMENT already includes `Read`/`Bash`.
  No tool-policy changes.
- Pure function; unit-tested by asserting the pointer + filenames appear for PLAN
  and IMPLEMENT and are absent for VERIFY.

### B. Curator + diff capture (write side) — `src/domain/prompts.py` (LEARN)

The LEARN prompt is strengthened so the curator updates project memory:

- Edit `CLAUDE.md`/`AGENTS.md` (keep concise, target ≤~120 lines) and add/update
  `docs/adr/` entries.
- Propose **additions and deletions** for *durable* learnings from this run
  (new conventions, gotchas, architectural decisions) — write-time curation
  prevents memory rot.

LEARN tools remain `["Read", "Write"]` (curator already had Write).

### C. Durable artifact — domain model + persistence

New immutable Pydantic model `MemoryProposal`:

| field        | type        | notes                                            |
|--------------|-------------|--------------------------------------------------|
| `id`         | str (32)    | UUID hex                                          |
| `owner_id`   | str         | owner-scoped                                     |
| `run_id`     | str (32)    | indexed                                          |
| `project_id` | str (32)    | indexed                                          |
| `branch`     | str         | `agent/memory-<run_id>`                          |
| `diff`       | str         | unified diff text of memory paths                |
| `files`      | list[str]   | memory paths changed                             |
| `status`     | str         | `"proposed"` (A6b-2 adds applied/rejected)       |
| `created_at` | datetime    |                                                  |

Mirrors the established entity stack:

- `MemoryProposalRow` in `src/adapters/database/orm.py`
- `MemoryProposalRepository` in `src/adapters/database/repositories.py`
- UnitOfWork property `memory_proposals` in `src/adapters/database/uow.py`
  (+ protocol in `ports.py`)
- Alembic migration adding `memory_proposals` (with `ix_*_owner_id`, `run_id`,
  `project_id`), kept in parity with ORM metadata (the `test_migrations` gate).

This table is the seam A6b-2's review UI reads from.

### D. Git port additions — `src/adapters/git/{ports,local_git,fake}.py`

Two cohesive methods added to `GitPort`:

- `diff(workspace_path, *, paths: list[str]) -> str` — unified diff of the given
  paths in the working tree (for the artifact).
- `commit_to_branch(workspace_path, *, branch, base, paths, message) -> bool` —
  create `branch` off `base`, stage and commit only `paths`, return whether
  anything was committed (False on empty diff).

`push(workspace_path, branch, *, token=None)` already exists and is reused.
`fake.py` gets in-memory equivalents so workflow/activity tests need no real git.

### E. Workflow / activity wiring

A dedicated activity `capture_memory(payload)` mirrors `open_pr`. The workflow
calls it **after** the LEARN `run_stage` completes and **before** `_cleanup`.

`capture_memory` steps:

1. `diff` the memory paths. If empty → record a "no memory changes" run_event,
   return `{"outcome": "ok", "proposal_id": None}`.
2. `commit_to_branch` → `agent/memory-<run_id>` off the run base branch.
3. **Push-and-hold**: if a remote profile/token is available (reuse `open_pr`'s
   token-mint path), push the branch. Never merged. Local mode: skip push.
4. Persist a `MemoryProposal` via the repository.
5. Emit a run_event: `"memory proposal: N file(s) on agent/memory-<run_id>"`.

LEARN stays a normal `run_stage`; capture is a separate activity, matching the
PROVISION/PR pattern and keeping `run_stage` generic.

### F. API + testing

- Read-only `GET /runs/{run_id}/memory` returns the proposal in the standard
  `{success, data, error}` envelope (`data: null` when none exists). Owner-scoped
  via the UnitOfWork. Provides A6b-2 its data source and lets integration tests
  assert persistence.

## Data flow

```
PLAN  prompt (reads CLAUDE.md/AGENTS.md/docs/adr) ─┐
IMPLEMENT prompt (same pointer) ──────────────────┤ agents honor project memory
VERIFY / PR ──────────────────────────────────────┘
LEARN run_stage: curator edits memory files in workspace
        │
        ▼
capture_memory activity:
  git diff(memory paths) ──► unified diff
  commit_to_branch(agent/memory-<run>, base, memory paths)
  push-and-hold (if remote)
  persist MemoryProposal(status="proposed")
  run_event("memory proposal: N files …")
        │
        ▼
cleanup_workspace (workspace destroyed; proposal + branch survive)
```

## Error handling

- Empty memory diff → no branch, no proposal; a benign run_event is recorded.
- Push failure (no remote / bad token) in local mode → branch + DB proposal still
  persist; the diff is never lost. Push errors are logged, not fatal to the run.
- Curator edits outside memory paths → silently ignored by path-scoped capture.
- `GET /runs/{id}/memory` with no proposal → `200 {success:true, data:null}`.

## Testing

| Layer        | Tests                                                                 |
|--------------|----------------------------------------------------------------------|
| Unit         | prompts: PLAN/IMPLEMENT contain pointer, VERIFY does not; LEARN prompt mentions additions+deletions and memory files |
| Unit         | `MemoryProposal` model construction/immutability                     |
| Unit         | fake git `diff` + `commit_to_branch` (empty + non-empty)             |
| Unit (repo)  | `MemoryProposalRepository` round-trip + owner scoping                |
| Unit         | migration ↔ ORM metadata parity (`memory_proposals` present)         |
| Workflow     | LEARN → `capture_memory` persists a proposal + emits a run_event; empty-diff path persists nothing |
| Integration  | `GET /runs/{id}/memory` envelope (present + absent)                  |

80% coverage gate applies. TDD throughout.

## Build order (parallel-worktree lanes)

- **Wave 1 (independent):**
  - Lane P — prompts (A, B): pointer + curator prompt. Pure domain.
  - Lane M — persistence (C): model + orm + repo + uow + migration.
  - Lane G — git port (D): `diff` + `commit_to_branch` + fake.
- **Wave 2 (depends on M + G):**
  - Lane W — `capture_memory` activity + workflow wiring (E).
- **Wave 3 (depends on M, W):**
  - Lane A — `GET /runs/{id}/memory` endpoint (F).

Each lane: TDD, runs the suite in its worktree, one PR per lane into the
integration branch `feature/a6b-1-project-memory`, then a final integration PR
into `main`.
