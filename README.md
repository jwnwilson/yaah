# yaah

Self-hosted agent harness: virtual dev teams (lead, engineers, QA, …) that take
tickets from a kanban board and produce reviewed PRs, in sandboxed containers,
on user-configurable models.

Design spec: `docs/specs/2026-06-12-yaah-design.md`

## Stack
Python 3.12 / uv / FastAPI / SQLAlchemy / Postgres / Temporal / React (UI in `ui/`, later phase).

## Dev
```bash
uv sync
docker compose up -d postgres
uv run pytest
uv run uvicorn --app-dir src interactors.api.app:create_app --factory --reload
```
