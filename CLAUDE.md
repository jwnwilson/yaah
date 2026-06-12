# yaah — Yet Another Agent Harness

A self-hosted platform for running **virtual dev teams** — role-based AI agents (team lead, architect, backend/frontend engineers, QA, devops) — against real repositories, driven from a visual kanban board of projects → epics → features → tasks. Agents work in sandboxed Docker containers with centrally managed secrets, permissions, skills, MCP servers, and models, produce reviewable PRs, and update persistent memory as they work.

- Design spec: [docs/specs/2026-06-12-yaah-design.md](docs/specs/2026-06-12-yaah-design.md)
- Current plan: [docs/plans/2026-06-12-yaah-a1-control-plane-foundation.md](docs/plans/2026-06-12-yaah-a1-control-plane-foundation.md)

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
ui/              # UI code
src/
  domain/        # pure business logic, no I/O
    models.py    # Project, WorkItem (epic/feature/task), Team, AgentDefinition, Run
    transitions.py  # work-item status state machine
    teams.py     # default team factory (lead + engineer + QA)
    errors.py    # typed persistence errors (RecordNotFound, IntegrityConflict, InvalidFilter)
    ports.py     # Repository / UnitOfWork protocols + PaginatedResult
  adapters/      # concrete port implementations
    database/    # orm.py (rows), repository.py (generic), repositories.py, uow.py, engine.py
  interactors/   # entry points: wiring only, no business logic
    api/         # FastAPI app factory, CrudRouter, routes, auth, settings
tests/
  unit/          # domain + repository/uow (SQLite in-memory)
  integration/   # API via TestClient
```

> Placement rules: ports in `domain/ports.py`; business logic in `domain/` (no argparse, no I/O, no adapter imports); port implementations in `adapters/`; wiring/startup in `interactors/`. No `scripts/` folder.

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
```

## Roadmap (phase A spine → C management plane → B full team)

A1 control-plane foundation (this plan) → A2 board UI → A3 Temporal pipeline + FakeAgentRuntime → A4 sandbox/egress proxy/GitHub App → A5 Claude Code runtime adapter + LiteLLM → A6 refinement chat + memory. Then C (secrets/capabilities/model/budget UIs), then B (full team roles, parallel engineers, RAG).
