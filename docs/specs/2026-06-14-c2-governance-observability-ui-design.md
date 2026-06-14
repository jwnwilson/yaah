# yaah C2 — Governance & Observability UIs (Design)

**Date:** 2026-06-14
**Status:** Approved design, pending implementation plan
**Phase:** C2 (management plane — observability + model config slice; part of Phase C in the yaah design)
**Depends on:** C1a (global `AppLayout` + `ManageLayout` + `ResourceTable`/`ConfirmDialog` + React Query/MSW conventions), A5c-3d-1 (`AuditEvent` + run audit endpoint), A5d (`UsageRecord` + usage endpoints), A6b (`MemoryProposal` + inline `MemoryProposalCard`), A1 (teams/agents CRUD) — all merged to `main`.

## 1. Problem & goal

C1a delivered the management-plane shell (global header, `Manage` area) and three registry screens (Secrets, Skills, MCP servers). The rest of Phase C's observability and configuration surfaces still have **backends but no UI**:

- **Usage/cost** — `UsageRecord` + `/runs/{id}/usage`, `/work-items/{id}/usage`, `/projects/{id}/usage` exist, but there is no cross-run budget view.
- **Audit** — `AuditEvent` + `/runs/{id}/audit` exist, but no cross-run audit log viewer.
- **Model config** — agents carry a `model_alias`, and teams/agents CRUD exist (`/teams`, `/teams/{id}/agents`, `PATCH /agents/{id}`), but there is no UI to view or change an agent's model or grants.
- **Memory** — `MemoryProposal` + apply/reject endpoints exist and an inline `MemoryProposalCard` renders the latest proposal in the run section, but there is no history/diff viewer across proposals.

C2 delivers four owner-scoped Manage screens — **Budget**, **Models** (agents), **Audit log**, and **Memory proposals** — plus the three small list endpoints the cross-run views require.

### C2 success criterion

> From the running app, open **Manage → Budget** and see total cost/tokens for the workspace with a group-by toggle (stage/model/role); open **Models**, pick a team, and change an agent's `model_alias` (persists via `PATCH /agents/{id}`); open **Audit** and page through tool grant/deny events filtered by action; open **Memory** and browse all proposals (proposed/applied/rejected) with their diffs. All views are owner-scoped and survive a reload.

## 2. Scope

### In scope

**Backend (3 list endpoints, each following the existing `project_usage` pattern in `usage.py`):**
- **`GET /usage`** — owner-scoped global rollup. Optional `project_id`, `since`, `until`, `group_by` (`stage`|`agent_role`|`model`). Reuses `_payload`/`rollup`/`group_by` helpers.
- **`GET /audit`** — owner-scoped, newest-first, paginated (`page_size`/`page_number`). Optional `run_id` and `action` filters.
- **`GET /memory-proposals`** — owner-scoped, newest-first, paginated. Optional `project_id` and `status` filters.

**Frontend (4 screens under `/manage/*`, sidebar nav added to `ManageLayout`):**
- **`/manage/usage` — Budget**: totals card (cost_usd, total/input/output/cache tokens), group-by toggle, optional date-range + project filter. Read-only.
- **`/manage/models` — Models**: team selector → agents table (role · name · `model_alias` · runtime) → edit dialog over `PATCH /agents/{id}` (model_alias, allowed_tools, skill/secret/mcp grants). Reuses existing agents CRUD; no agent create/delete here (lifecycle stays with team defaults).
- **`/manage/audit` — Audit log**: paginated table (time · actor · action badge · run link · detail), action filter.
- **`/manage/memory` — Memory proposals**: history table (status badge · project · files · time) with an expandable diff viewer, reusing a shared `MemoryDiff` component extracted from `MemoryProposalCard`.

**Tests & gates:** pytest integration per new endpoint (owner-scoping, each filter, pagination, empty case); Vitest + Testing Library + MSW per screen (list render, filter/group toggles, empty + error states, agents edit mutation); `make coverage` (80%) + `make lint` + UI `npm run lint`/`build` green.

### Out of scope (later slices / phases)
- **Model registry / validated alias picker** — `model_alias` stays a free-text field edited per agent; a registry of allowed models is deferred (YAGNI for single-user local).
- **Agent create/delete and team management** — only editing existing agents here.
- **Project-scoped audit** — `AuditEvent` has no `project_id`; the viewer is owner-global with an optional `run_id` filter. Adding `project_id` to audit is deferred.
- **LiteLLM gateway configuration UI** — gateway is env-configured (`YAAH_*`); not surfaced here.
- **Budget *limits*/enforcement, alerts** — Budget is read-only reporting; enforcement is a later slice.
- **Memory proposal apply/reject from the history screen** — actions remain on the inline run card; the history screen is read/inspect only.
- **Run inspector, autonomy dial** — later Phase C slices.

## 3. Decisions log

| Decision | Choice | Rationale |
|---|---|---|
| New endpoints | **3 owner-scoped list endpoints mirroring `project_usage`** | Repos already expose `.list(filters, page_size)` with auto owner-scoping; no schema change needed |
| Audit scope | **Owner-global + optional `run_id` filter (no project filter)** | `AuditEvent` lacks `project_id`; project resolution via runs is unjustified for single-user local |
| Usage global view | **New `GET /usage` reusing existing payload helpers** | Cross-run budget needs an owner-scoped rollup; per-project endpoint already exists for drill-down |
| Model config | **Edit existing agents (model_alias + grants), no create/delete** | Teams/agents CRUD exists; agent lifecycle stays with default-team factory (YAGNI) |
| Memory screen | **Dedicated read-only history + shared `MemoryDiff` component** | Inline card shows only the latest proposal; extracting the diff renderer avoids duplication (DRY) |
| Memory actions | **Apply/reject stay on the inline run card** | Keeps the history screen a pure viewer; one place owns the mutation |
| Navigation | **Add Budget · Models · Audit · Memory to the `ManageLayout` sidebar** | Reuses the C1a shell; no new layout primitives |
| Component reuse | **`ResourceTable` + `ConfirmDialog` + new shared `MemoryDiff`** | Matches C1a; per-screen specifics (group toggle, edit dialog) stay local |
| Delivery | **One spec, 4 PRs:** PR1 backend endpoints; PR2 Budget+Audit; PR3 Models; PR4 Memory + diff extraction | Keeps each PR focused and reviewable; backend lands first so frontend can mock against real shapes |

## 4. Data shapes (existing — no new models)

- **`TokenUsage`**: `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `cost_usd`, computed `total_tokens`. Usage payload: `{ totals, group_by?, groups? }` (+ `breakdown` for run view).
- **`AuditEvent`**: `id`, `owner_id`, `run_id`, `stage?`, `actor`, `action` (`capability_granted`|`tool_allowed`|`tool_denied`), `detail` (dict), `created_at`.
- **`AgentDefinition`**: `id`, `team_id`, `role`, `name`, `persona`, `model_alias`, `runtime`, `purpose`, `system_prompt`, `allowed_tools`, `skill_ids`, `mcp_server_ids`, `secret_ids`.
- **`MemoryProposal`**: `id`, `owner_id`, `run_id`, `project_id`, `branch`, `diff` (unified-diff string), `files` (paths), `status` (`proposed`|`applied`|`rejected`), `pr_url?`, `resolved_at?`, `created_at`.

## 5. API envelope

All endpoints use the standard `{ success, data, error, meta? }` envelope. List endpoints set `meta: { total, page_size, page_number }`. Owner scope is enforced by the UnitOfWork on every repository query (auth mode `dev` → `dev-user`).

## 6. Testing strategy

- **Backend (pytest, SQLite in-memory):** for each endpoint — owner-scoping isolation (another owner's rows excluded), each optional filter, pagination boundaries, and the empty result. `since > until` → 422 on `/usage`. Invalid `group_by` → 422. Invalid `action`/`status` → 422.
- **Frontend (Vitest + MSW):** per screen — list render from mocked envelope, filter/group toggles re-query, empty state, error state; Models edit dialog fires `PATCH` and invalidates the query; `MemoryDiff` renders a unified diff and is shared by the inline card (snapshot parity).
- **Coverage:** `make coverage` ≥ 80%; UI suite green.
