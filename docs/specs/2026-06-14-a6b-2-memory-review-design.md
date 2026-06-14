# A6b-2 — Memory-Diff Review & Apply (Design)

**Status:** approved
**Date:** 2026-06-14
**Parent:** A6 (memory), see [docs/specs/2026-06-12-yaah-design.md](2026-06-12-yaah-design.md) §8
**Predecessor:** A6b-1 project memory loop (merged)

## Goal

Let a human review proposed project-memory changes and **apply** or **reject**
them from the board, and **auto-apply in `full_auto`** autonomy. Builds directly
on A6b-1, which already persists a `MemoryProposal` (with a
`proposed → applied/rejected` status enum) and emits one per successful run via
the `capture_memory` activity.

## Core constraint

The run workspace is destroyed at cleanup, but the `agent/memory-<run>` branch
survives — in the local repo's `.git` (local profile) and on origin (remote,
pushed). Per design §7, the GitHub App **cannot merge `main`** (branch rulesets
require a PR + human review; the App is not on the bypass list). Therefore
"apply" is **asymmetric**:

- **local profile** → fast-forward the base branch to the memory branch.
- **remote profile** → open a PR for the memory branch (a human merges on GitHub).

## Scope

### In scope

- `GitPort.merge_into_base` (local fast-forward / merge) + `FakeGit` impl.
- A `MemoryApplier` interactor encapsulating local-merge vs remote-PR.
- Auto-apply in `capture_memory` for `full_auto`; `proposed` otherwise.
- `MemoryProposal` gains `pr_url` and `resolved_at`; apply/reject transitions.
- `POST /runs/{run_id}/memory/apply` and `/reject` endpoints.
- Board UI: a memory-proposal card in the run section with diff + Apply/Reject.

### Out of scope

- Memory-branch cleanup / garbage collection.
- Conflict *resolution* UI (we only detect and report conflicts).
- Editing the diff before applying.
- Role memory repo (A6b-3).

## Components

### A. Apply mechanics — `GitPort` + forge

New `GitPort` method:

```
merge_into_base(repo_ref, *, branch, base, token=None) -> bool
```

- If `branch` is a descendant of `base` (the common case — the memory branch is
  `base` + memory commits, and base has not moved), **fast-forward** `base` to
  `branch` by updating the base ref. Returns `True`.
- If `base` has diverged, attempt a real merge in an internal detached worktree;
  on conflict raise `GitError` (apply fails; the proposal stays `proposed`; the
  error is surfaced).
- `repo_ref` is the managed repo (`project.local_path` for local; the clone URL
  for remote, though remote does not use this method — see below).

`FakeGit` records `merge_into_base` calls in a `merged_into_base` list and
returns a configurable result so tests need no real git.

**Remote apply** does not use `merge_into_base`; it calls the existing
`GitForgePort.open_pull_request(head=branch, base, title, body) -> str` (PR URL).

### B. `MemoryApplier` interactor

A small, pure-of-routing service holding the local-vs-remote branch, constructed
from settings with injected `GitPort` + `GitForgePort` (mirroring how the worker
builds its adapters):

```
class MemoryApplier:
    def __init__(self, git, forge, *, profile): ...
    def apply(self, proposal, *, repo_ref, base) -> MemoryProposal:
        # local : git.merge_into_base(repo_ref, branch=proposal.branch, base=base)
        #         -> returns proposal.model_copy(status=APPLIED, resolved_at=now)
        # remote: pr_url = forge.open_pull_request(head=proposal.branch, base=...)
        #         -> returns proposal.model_copy(status=APPLIED, pr_url=pr_url, resolved_at=now)
```

It returns an updated (immutable) `MemoryProposal`; the caller persists it. Both
the apply endpoint and `capture_memory`'s auto path use this one code path.

> Execution is **synchronous** (the user waits on the apply click; the run
> workflow is already finished by apply time). The applier is unit-tested with
> fakes. The API process constructs `git`/`forge` from settings via a dependency,
> the same way the Temporal worker does.

### C. Status lifecycle + persistence

`MemoryProposal` gains two nullable fields:

| field         | type              | meaning                                |
|---------------|-------------------|----------------------------------------|
| `pr_url`      | `str \| None`     | set when a remote apply opens a PR     |
| `resolved_at` | `datetime \| None`| set on apply or reject                 |

`MemoryProposalRow` + the Alembic migration add both columns (kept in
ORM-metadata parity with the `test_migrations` gate).

Transitions (idempotency mirrors run gates): apply/reject are valid only from
`proposed`; acting on an `applied`/`rejected` proposal → HTTP 409.

### D. Auto-apply at run time — `capture_memory`

The workflow passes `autonomy` and `repo_ref` into the `capture_memory` payload.
After persisting the proposal, `capture_memory`:

- `autonomy == full_auto` → call `MemoryApplier.apply(...)`, persist the returned
  `applied` proposal (local merge happens in the still-alive workspace's repo;
  remote opens a PR), emit a run_event (`"memory applied …"` / `"memory PR opened …"`).
- otherwise → leave `status=proposed` (a run_event already announces the proposal).

Auto-apply is **best-effort**: any failure leaves the proposal `proposed`
(degrades to manual review) and records a run_event; it never fails the run.

### E. API

- `POST /runs/{run_id}/memory/apply` → load the proposal (404 if none); 409 if not
  `proposed`; run `MemoryApplier.apply(...)` (needs the run's project for
  `repo_ref`/`base`); persist + return the proposal. Local merge conflict /
  remote PR failure → enveloped 409 with the error message, status unchanged.
- `POST /runs/{run_id}/memory/reject` → 404/409 as above; set `rejected` +
  `resolved_at`; persist + return. The branch is left in place.

Both return the standard `{success, data, error}` envelope.

### F. UI — board run section

A `MemoryProposalCard` rendered inside the existing `RunSection` (TicketPanel),
fed by `GET /runs/{id}/memory`:

- shows changed `files` and the collapsible `diff`;
- `status=proposed` → **Apply** / **Reject** buttons (mirroring `RunActions`),
  invalidating the memory query on success;
- `applied`/`rejected` → a status badge, plus a PR link when `pr_url` is set.

New `useMemoryProposal` hook + `ui/src/lib/api/memory.ts` mirroring the existing
run hooks/clients.

## Data flow

```
run completes ─► capture_memory persists MemoryProposal(proposed)
                   │
                   ├─ full_auto ─► MemoryApplier.apply ─► local ff base / remote PR
                   │                └─ persist applied (+pr_url), run_event
                   └─ gated ─► stays proposed
                                   │
human opens TicketPanel ─► MemoryProposalCard (GET /runs/{id}/memory)
   │  Apply ─► POST /runs/{id}/memory/apply ─► MemoryApplier.apply ─► applied
   │  Reject ─► POST /runs/{id}/memory/reject ─► rejected
```

## Error handling

- Apply/reject on non-`proposed` → 409. No proposal → 404.
- Local merge conflict / base divergence → `GitError` → 409, status unchanged.
- Remote PR failure → enveloped error, status unchanged.
- `full_auto` auto-apply failure → proposal stays `proposed`, run_event records it;
  the run still completes.

## Testing

| Layer       | Tests                                                                       |
|-------------|-----------------------------------------------------------------------------|
| Unit        | `FakeGit.merge_into_base`; `MemoryApplier` local-merge vs remote-PR; lifecycle transitions reject non-proposed |
| Unit        | `capture_memory` applies in `full_auto`, stays `proposed` otherwise; auto-apply failure is non-fatal |
| Unit (repo) | `MemoryProposal` new fields round-trip                                       |
| Unit        | migration ↔ ORM metadata parity (new columns)                               |
| Integration | apply success, reject success, 409 non-proposed, 404 absent                  |
| Workflow    | `full_auto` run → proposal `applied`; gated run → `proposed`                 |
| UI          | card renders diff + files; Apply/Reject call endpoints and invalidate; badge + PR link for resolved |

80% coverage gate; TDD throughout.

## Build order (parallel-worktree lanes)

- **Wave 1 (independent):**
  - Lane G — `GitPort.merge_into_base` + `FakeGit`.
  - Lane M — `MemoryProposal` `pr_url`/`resolved_at` + ORM + migration.
- **Wave 2 (needs G + M):**
  - Lane S — `MemoryApplier` interactor + auto-apply wiring in `capture_memory`
    (+ `autonomy`/`repo_ref` in the workflow payload).
- **Wave 3 (needs S):**
  - Lane API — apply/reject endpoints.
  - Lane UI — `MemoryProposalCard` + hook + api client.

Single integration branch `feature/a6b-2-memory-review`; one PR into `main`.
