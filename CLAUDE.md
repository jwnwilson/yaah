# yaah — Yet Another Agent Harness

A self-hosted platform for running **virtual dev teams** — role-based AI agents (team lead, architect, backend/frontend engineers, QA, devops) — against real repositories, driven from a visual kanban board of projects → epics → features → tasks. Agents work in sandboxed Docker containers with centrally managed secrets, permissions, skills, MCP servers, and models, produce reviewable PRs, and update persistent memory as they work.

- Design spec: [docs/specs/2026-06-12-yaah-design.md](docs/specs/2026-06-12-yaah-design.md)
- **Where we are (read first): [docs/project-history.md](docs/project-history.md)** — consolidated status, what's shipped, gaps
- Current plan: [docs/plans/2026-06-12-yaah-a1-control-plane-foundation.md](docs/plans/2026-06-12-yaah-a1-control-plane-foundation.md)

## Workflow (read first)

**All work happens in a git worktree and ships via a reviewed PR. Never commit or push directly to `main`.**

- Start every task in an isolated worktree off the latest `main`:
  `git worktree add -b <type>/<slug> ../yaah-<slug> origin/main`. Do the work there, not in the primary checkout.
- `main` only advances by merging a reviewed PR — no direct commits, no bundled auto-commits with junk titles.
- One PR = one focused change: a clear `<type>: <description>` title, a summary, and a test plan. Keep unrelated edits out.
- Before opening the PR, get `make coverage` (80% gate) and `make lint` green, then `git push -u origin <branch>` and open the PR with `gh pr create`.

## Stack

- Python ≥ 3.12, package manager: `uv`
- FastAPI + uvicorn (API), Pydantic v2, pydantic-settings (env prefix `YAAH_`)
- SQLAlchemy 2.0 (sync) + Postgres 16 (SQLite in-memory for tests)
- Temporal (run orchestration — one workflow per ticket run; phase A3+)
- React + Vite + Tailwind (board UI in `ui/`; phase A2+)
- pytest + httpx; 80% coverage gate

## Architecture

> **When designing tasks that touch persistence or the API layer, first read
> [docs/architecture.md](docs/architecture.md)** — it defines the repository/UnitOfWork,
> owner-scoping, and CrudRouter patterns (adapted from hexrepo) that new code must follow.

Hexagonal, three layers — domain logic never touches I/O:

```
ui/src/          # React + Vite frontend (pnpm)
  app/             # app shell: providers, router, layout, error boundary
  modules/         # feature/domain slices (board, runs, manage, team, …); each owns its components + hooks + api
  components/ui/    # design-system primitives (Button, Dialog, Card, …) + shared composed components
  lib/api/         # typed envelope API client + per-domain modules + React Query key factories
src/
  domain/        # pure business logic, no I/O — entity models live with the logic that owns them
    base.py         # shared id/timestamp factories (new_id, utc_now)
    projects/       # task-management domain: projects.py (Project + AutonomyLevel), work_items.py
                    #   (WorkItem + kind/status enums), epics.py (epic-board read-model); re-exported via __init__
    runs.py         # Run + RunStage/RunStatus/RunEvent
    messages.py     # Message + inter-agent mailbox enums
    audit.py        # AuditEvent + AuditAction
    attachments.py  # WorkItemAttachment + attachment policy
    notifications.py # Notification model + event→notification policy
    usage.py        # UsageRecord + TokenUsage rollups
    refinement.py   # ChatSession/ChatMessage + refinement proposal policy
    errors.py       # typed persistence errors (RecordNotFound, IntegrityConflict, InvalidFilter)
    transitions/    # state-progression rules (work-item + run state machines, run-stage pipeline)
    orchestration/  # lead-driven orchestration DTOs, guards, mappings + orchestrator prompt/parse contract
    agent/          # agent domain: models.py (AgentRole, Team, AgentDefinition), teams.py (default team
                    #   factory), memory.py (RoleMemoryEntry, MemoryProposal + project-memory helpers),
                    #   capability_grants.py (Skill, McpServer, Secret), + execution policy (runtime DTOs,
                    #   capability manifest assembly, prompts, CLI invocation)
  adapters/      # concrete port implementations
    database/    # ports.py (Repository/UnitOfWork protocols + PaginatedResult), orm.py, repository.py, repositories.py, uow.py, engine.py
  interactors/   # entry points: wiring only, no business logic
    api/         # FastAPI app factory, routes, auth, settings
  lib/           # reusable, app-agnostic modules (CrudRouter)
tests/
  unit/          # domain + repository/uow (SQLite in-memory)
  integration/   # API via TestClient
```

> Placement rules: persistence ports (Repository/UnitOfWork protocols) live with their impl in `adapters/database/ports.py`; business logic in `domain/` (no argparse, no I/O, no adapter imports), with each entity model co-located in the domain module that owns it (no central `models.py`); port implementations in `adapters/`; reusable app-agnostic modules in `lib/`; wiring/startup in `interactors/`. No `scripts/` folder.

## Key conventions

- **Immutability**: Pydantic models updated via `model_copy(update={...})`, never mutated.
- **API envelope**: every response is `{success, data, error}` (+ `meta` for pagination).
- **Owner scoping**: every owned row carries `owner_id`; the UnitOfWork applies it as a required filter on every repository query. Auth mode `dev` injects `dev-user`; Auth0 arrives with the remote profile.
- **Status changes** go through `domain/transitions.validate_transition` — invalid transitions return HTTP 409.
- **Run IDs / entity IDs** are UUID hex strings (32 chars).
- **TDD**: write the failing test first; AAA structure; descriptive behavior names.
- Commit format: `<type>: <description>` (feat/fix/refactor/docs/test/chore/perf/ci).

## Dev commands

```bash
uv sync                      # install
docker compose up -d postgres
uv run pytest                # all tests
make coverage                # tests + 80% gate
uv run uvicorn --app-dir src interactors.api.app:create_app --factory --reload
docker compose up -d temporal     # Temporal dev server (UI on :8233)
make worker                       # run the Temporal worker (pipeline executor)
ANTHROPIC_API_KEY=... docker compose up -d --build worker   # real agent worker (auto-selects claude)
docker compose up -d litellm   # LiteLLM gateway on :4000 (set YAAH_LITELLM_BASE_URL=http://localhost:4000)
# Deploy: push to main -> GitHub Actions (see docs/deployment.md). Manual: gh workflow run "Deploy Backend"

# UI (run from ui/; pnpm is the package manager — never npm)
cd ui && pnpm install        # install UI deps
pnpm dev                     # Vite dev server on :5173 (proxies /api -> :8000)
pnpm lint                    # eslint + tsc --noEmit
pnpm test                    # vitest unit tests
pnpm build                   # production build (tsc -b && vite build)
```

## Roadmap (phase A spine → C management plane → B full team)

A1 control-plane foundation (this plan) → A2 board UI → A3 Temporal pipeline + FakeAgentRuntime → A4 sandbox/egress proxy/GitHub App → A5 Claude Code runtime adapter + LiteLLM → A5d token/usage tracking → A5e notification system → A6 refinement chat + memory. Then C (secrets/capabilities/model/budget UIs — budget builds on A5d usage data), then B (full team roles, parallel engineers, RAG).

> **Orchestration direction (see [ADR-0002](docs/adr/0002-lead-driven-orchestration.md), implemented 2026-06-15):** the team lead **is** the **orchestrator agent** — it dispatches other agents and triggers a completion monitor — and `OrchestratorWorkflow`/`AgentWorkflow` is now the **sole run path** (the fixed `PLAN→IMPLEMENT→VERIFY` `RunWorkflow` was removed). Agents run as **Temporal child-workflow actors** with signal-fed mailboxes; **Temporal stays the durable executor** (orchestrator-worker pattern). Current shape is one actor per role per wave; true concurrent waves + live inter-agent messaging are the **parallel-engineers** spec (Phase B). This supersedes the original "workflow is the sole supervisor" stance in the design spec. ADRs live in `docs/adr/`.

> **A5 status (single-user local):** A4a (GitHub App + workspaces + real PR), A5a/b (Claude Code runtime in a containerized worker), and A5c (agent capability model — C1 grants, C2 runtime composition, C3a encrypted secret values + scoped injection, C3b-1 LiteLLM routing, C3d-1/2 capability + tool audit) are merged. **C3c (egress proxy / credential broker) is descoped:** for single-user local, secret access is controlled by per-agent grants + per-stage scoped injection, and open egress is acceptable; the network chokepoint / zero-secret-container work returns only if/when multi-tenant or remote hardening is needed.
