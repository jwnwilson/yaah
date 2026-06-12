# A2 Board UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the yaah A2 board UI — a React SPA kanban board over projects/work-items/runs — plus the read-write run backend endpoints it needs.

**Architecture:** Backend first (small additions to the existing FastAPI/hexagonal app: a run-status state machine + cancel/approve/reject/PATCH routes), then a greenfield `ui/` React SPA where TanStack Query is the single source of truth, dnd-kit drives kanban transitions with optimistic update + 409 rollback, and a thin `lib/api` layer is the only code that knows the `{success, data, error}` envelope.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy (existing) · React 18 + Vite + TypeScript (strict) + Tailwind + TanStack Query + React Router + dnd-kit + shadcn-style components · vitest + React Testing Library + MSW + Playwright.

**Spec:** `docs/specs/2026-06-12-a2-board-ui-design.md`

**Precondition:** A1.5 hexrepo refactor has landed (UnitOfWork, repositories, CrudRouter, enveloped exception handlers, post-refactor `work_items.py`/`runs.py`). Verify before starting: `git log --oneline | grep -i 'UnitOfWork\|CrudRouter'` returns commits.

---

## Conventions for every task

- **TDD:** write the failing test, run it red, implement minimally, run it green, commit.
- **Backend tests:** `uv run pytest <path> -v`. **Frontend tests:** `cd ui && npm test -- <path>`.
- **Commit message format:** `<type>: <description>` (feat/fix/refactor/docs/test/chore).
- **Backend route style:** mirror `src/interactors/api/routes/work_items.py` exactly — `uow: UnitOfWork = Depends(get_uow)`, `with uow.transaction():`, return `ok(dto.model_dump(mode="json"))`. Never try/except persistence errors in routes; the app factory's handlers map `RecordNotFound`→404 and `InvalidTransition`→409.
- **Immutability:** update DTOs via `model_copy(update={...})`, never mutate.

---

# Part A — Backend: read-write runs

The `Run` model (`src/domain/models.py`) already has: `id, owner_id, task_id, team_id, status, stage, branch, pr_url, cost_usd, created_at`. `RunStatus` = `pending, running, awaiting_approval, done, failed, blocked, cancelled`. `RunRepository` and `uow.runs` already exist with `get`/`update`. We add a state machine and four routes.

## Task A1: Run-status state machine

**Files:**
- Create: `src/domain/run_transitions.py`
- Test: `tests/unit/test_run_transitions.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_run_transitions.py
import pytest

from domain.models import RunStatus as R
from domain.run_transitions import validate_run_transition
from domain.transitions import InvalidTransition


def test_pending_can_be_cancelled():
    validate_run_transition(R.PENDING, R.CANCELLED)  # no raise


def test_awaiting_approval_can_be_approved_to_done():
    validate_run_transition(R.AWAITING_APPROVAL, R.DONE)


def test_awaiting_approval_can_be_rejected_to_failed():
    validate_run_transition(R.AWAITING_APPROVAL, R.FAILED)


def test_done_is_terminal():
    with pytest.raises(InvalidTransition):
        validate_run_transition(R.DONE, R.CANCELLED)


def test_pending_cannot_jump_to_done():
    with pytest.raises(InvalidTransition):
        validate_run_transition(R.PENDING, R.DONE)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_run_transitions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'domain.run_transitions'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/domain/run_transitions.py
from domain.models import RunStatus as R
from domain.transitions import InvalidTransition

_ALLOWED: dict[R, set[R]] = {
    R.PENDING: {R.RUNNING, R.CANCELLED},
    R.RUNNING: {R.AWAITING_APPROVAL, R.DONE, R.FAILED, R.BLOCKED, R.CANCELLED},
    R.AWAITING_APPROVAL: {R.DONE, R.FAILED, R.CANCELLED},
    R.BLOCKED: {R.RUNNING, R.CANCELLED},
    R.DONE: set(),
    R.FAILED: set(),
    R.CANCELLED: set(),
}


def validate_run_transition(src: R, dst: R) -> None:
    if dst not in _ALLOWED[src]:
        raise InvalidTransition(f"cannot move run from {src} to {dst}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_run_transitions.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/domain/run_transitions.py tests/unit/test_run_transitions.py
git commit -m "feat: run-status state machine"
```

## Task A2: Cancel-run endpoint

**Files:**
- Modify: `src/interactors/api/routes/runs.py`
- Test: `tests/integration/test_runs_api.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/integration/test_runs_api.py`. The file already provides `make_client()` and
`_ready_task(c) -> (task_id, team_id, project_id)`. Add a small helper to start a run, then the tests:

```python
def _start_run(c: TestClient) -> dict:
    task_id, _team_id, _pid = _ready_task(c)
    return c.post(f"/work-items/{task_id}/runs").json()["data"]  # status "pending"


def test_cancel_run_moves_it_to_cancelled():
    c = make_client()
    run = _start_run(c)
    resp = c.post(f"/runs/{run['id']}/cancel")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "cancelled"


def test_cancel_unknown_run_is_404():
    c = make_client()
    resp = c.post("/runs/deadbeef/cancel")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_runs_api.py -k cancel -v`
Expected: FAIL — 404/405 because the route does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add to `src/interactors/api/routes/runs.py` (add imports `RunStatus` from `domain.models` and `validate_run_transition` from `domain.run_transitions`):

```python
@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        run = uow.runs.get(run_id)  # owner-scoped -> 404
        validate_run_transition(run.status, RunStatus.CANCELLED)  # -> 409
        result = uow.runs.update(run_id, run.model_copy(update={"status": RunStatus.CANCELLED}))
    return ok(result.model_dump(mode="json"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_runs_api.py -k cancel -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/interactors/api/routes/runs.py tests/integration/test_runs_api.py
git commit -m "feat: cancel-run endpoint"
```

## Task A3: Approve and reject gate endpoints

**Files:**
- Modify: `src/interactors/api/routes/runs.py`
- Test: `tests/integration/test_runs_api.py`

- [ ] **Step 1: Write the failing test**

A freshly-started run is `pending`, so to exercise the gate we seed an `awaiting_approval` run
directly through the UoW. The `TestClient` exposes the app at `c.app`, whose
`state.session_factory` we reuse. Add a helper + tests:

```python
from domain.models import Run, RunStatus
from adapters.database.uow import SqlUnitOfWork


def _seed_awaiting_run(c: TestClient) -> str:
    task_id, team_id, _pid = _ready_task(c)
    uow = SqlUnitOfWork(c.app.state.session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        run = uow.runs.create(
            Run(owner_id="dev-user", task_id=task_id, team_id=team_id,
                status=RunStatus.AWAITING_APPROVAL)
        )
    return run.id


def test_approve_gate_moves_run_to_done():
    c = make_client()
    run_id = _seed_awaiting_run(c)
    resp = c.post(f"/runs/{run_id}/approve")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "done"


def test_reject_gate_moves_run_to_failed():
    c = make_client()
    run_id = _seed_awaiting_run(c)
    resp = c.post(f"/runs/{run_id}/reject")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "failed"


def test_approve_pending_run_is_409():
    c = make_client()
    run = _start_run(c)  # pending
    resp = c.post(f"/runs/{run['id']}/approve")
    assert resp.status_code == 409
```

> The auth-bypass owner id is `dev-user` (see `interactors/api/auth.py`). Confirm that literal
> when writing the seed helper.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_runs_api.py -k "approve or reject" -v`
Expected: FAIL — routes missing.

- [ ] **Step 3: Write minimal implementation**

Add to `src/interactors/api/routes/runs.py`:

```python
def _gate(run_id: str, dst: RunStatus, uow: UnitOfWork) -> dict:
    with uow.transaction():
        run = uow.runs.get(run_id)
        validate_run_transition(run.status, dst)
        result = uow.runs.update(run_id, run.model_copy(update={"status": dst}))
    return ok(result.model_dump(mode="json"))


@router.post("/runs/{run_id}/approve")
def approve_run(run_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    return _gate(run_id, RunStatus.DONE, uow)


@router.post("/runs/{run_id}/reject")
def reject_run(run_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    return _gate(run_id, RunStatus.FAILED, uow)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_runs_api.py -k "approve or reject" -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/interactors/api/routes/runs.py tests/integration/test_runs_api.py
git commit -m "feat: run approve/reject gate endpoints"
```

## Task A4: Edit-run-fields endpoint (PATCH)

**Files:**
- Modify: `src/interactors/api/routes/runs.py`
- Test: `tests/integration/test_runs_api.py`

- [ ] **Step 1: Write the failing test**

```python
def test_patch_run_edits_metadata_only():
    c = make_client()
    run = _start_run(c)
    resp = c.patch(f"/runs/{run['id']}", json={"branch": "agent/x", "stage": "implement"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["branch"] == "agent/x"
    assert data["stage"] == "implement"
    assert data["status"] == "pending"  # PATCH never changes status


def test_patch_run_ignores_status_field():
    c = make_client()
    run = _start_run(c)
    resp = c.patch(f"/runs/{run['id']}", json={"status": "done"})
    # status is not a field on UpdateRun, so FastAPI ignores it; run stays pending
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "pending"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_runs_api.py -k patch_run -v`
Expected: FAIL — route missing.

- [ ] **Step 3: Write minimal implementation**

Add to `src/interactors/api/routes/runs.py` (add `from pydantic import BaseModel` at top if absent):

```python
class UpdateRun(BaseModel):
    stage: str | None = None
    branch: str | None = None
    pr_url: str | None = None


@router.patch("/runs/{run_id}")
def patch_run(run_id: str, body: UpdateRun, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        run = uow.runs.get(run_id)
        result = uow.runs.update(run_id, run.model_copy(update=body.model_dump(exclude_none=True)))
    return ok(result.model_dump(mode="json"))
```

> `UpdateRun` has no `status` field, so a client-sent `status` is dropped by Pydantic — status can never change via PATCH (spec §5.4).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_runs_api.py -k patch_run -v`
Expected: PASS.

- [ ] **Step 5: Commit + full backend gate**

```bash
uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80
git add src/interactors/api/routes/runs.py tests/integration/test_runs_api.py
git commit -m "feat: PATCH run metadata endpoint"
```
Expected: all tests pass, coverage ≥ 80%.

## Task A5: Single-item `GET /work-items/{id}` route

The board panel (Task D4) fetches one work item by id, but only a list route exists today
(`GET /projects/{project_id}/work-items`). Add the single-item read.

**Files:**
- Modify: `src/interactors/api/routes/work_items.py`
- Test: `tests/integration/test_work_items_api.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/integration/test_work_items_api.py` (reuse the file's existing client/setup helpers — read the top of the file for their names):

```python
def test_get_single_work_item():
    c = make_client()  # use this file's existing client helper name
    pid = c.post("/projects", json={"name": "p", "repo_url": "r"}).json()["data"]["id"]
    epic = c.post(f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E"}).json()["data"]
    resp = c.get(f"/work-items/{epic['id']}")
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == epic["id"]


def test_get_missing_work_item_404():
    c = make_client()
    resp = c.get("/work-items/deadbeef")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_work_items_api.py -k single_work_item -v`
Expected: FAIL — 404/405, route missing.

- [ ] **Step 3: Write minimal implementation**

Add to `src/interactors/api/routes/work_items.py`:

```python
@router.get("/work-items/{item_id}")
def get_item(item_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        item = uow.work_items.get(item_id)  # owner-scoped -> 404
    return ok(item.model_dump(mode="json"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_work_items_api.py -k work_item -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/interactors/api/routes/work_items.py tests/integration/test_work_items_api.py
git commit -m "feat: single-item GET /work-items/{id} route"
```

---

# Part B — Frontend scaffolding

All paths under `ui/`. Run commands from the `ui/` directory unless noted.

## Task B1: Scaffold Vite + React + TS + Tailwind

**Files:**
- Create: `ui/package.json`, `ui/vite.config.ts`, `ui/tsconfig.json`, `ui/tsconfig.node.json`, `ui/index.html`, `ui/tailwind.config.ts`, `ui/postcss.config.js`, `ui/src/main.tsx`, `ui/src/index.css`, `ui/src/app/App.tsx`, `ui/.gitignore`

- [ ] **Step 1: Create the project files**

`ui/package.json`:
```json
{
  "name": "yaah-ui",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest",
    "lint": "tsc -b --noEmit",
    "e2e": "playwright test"
  },
  "dependencies": {
    "@tanstack/react-query": "^5.59.0",
    "@dnd-kit/core": "^6.1.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.0"
  },
  "devDependencies": {
    "@playwright/test": "^1.48.0",
    "@testing-library/jest-dom": "^6.5.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/user-event": "^14.5.0",
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "autoprefixer": "^10.4.0",
    "jsdom": "^25.0.0",
    "msw": "^2.4.0",
    "postcss": "^8.4.0",
    "tailwindcss": "^3.4.0",
    "typescript": "^5.6.0",
    "vite": "^5.4.0",
    "vitest": "^2.1.0"
  }
}
```

`ui/vite.config.ts`:
```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://localhost:8000", changeOrigin: true } },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
```

`ui/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] },
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

`ui/tsconfig.node.json`:
```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true
  },
  "include": ["vite.config.ts"]
}
```

`ui/index.html`:
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>yaah</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`ui/tailwind.config.ts`:
```typescript
import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: [],
} satisfies Config;
```

`ui/postcss.config.js`:
```javascript
export default { plugins: { tailwindcss: {}, autoprefixer: {} } };
```

`ui/src/index.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

`ui/src/app/App.tsx`:
```tsx
export default function App() {
  return <div className="p-6 text-lg font-semibold">yaah</div>;
}
```

`ui/src/main.tsx`:
```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./app/App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

`ui/.gitignore`:
```
node_modules
dist
playwright-report
test-results
```

- [ ] **Step 2: Install and verify build**

Run:
```bash
cd ui && npm install && npm run build
```
Expected: install succeeds; `tsc -b && vite build` produces `ui/dist` with no type errors.

- [ ] **Step 3: Commit**

```bash
git add ui/package.json ui/package-lock.json ui/vite.config.ts ui/tsconfig.json ui/tsconfig.node.json ui/index.html ui/tailwind.config.ts ui/postcss.config.js ui/src ui/.gitignore
git commit -m "chore: scaffold ui (vite + react + ts + tailwind)"
```

## Task B2: Test harness (vitest setup + MSW)

**Files:**
- Create: `ui/src/test/setup.ts`, `ui/src/test/server.ts`, `ui/src/test/handlers.ts`, `ui/src/test/smoke.test.tsx`

- [ ] **Step 1: Write the failing test**

`ui/src/test/smoke.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import App from "../app/App";

test("renders app shell", () => {
  render(<App />);
  expect(screen.getByText("yaah")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- src/test/smoke.test.tsx`
Expected: FAIL — `setup.ts` / jest-dom matchers not found.

- [ ] **Step 3: Write the harness**

`ui/src/test/handlers.ts`:
```typescript
import { http, HttpResponse } from "msw";

// Per-test overrides use server.use(...). Default: empty list responses.
export const handlers = [
  http.get("/api/projects", () =>
    HttpResponse.json({ success: true, data: [], error: null, meta: { total: 0, page_size: 100, page_number: 1 } }),
  ),
];
```

`ui/src/test/server.ts`:
```typescript
import { setupServer } from "msw/node";
import { handlers } from "./handlers";

export const server = setupServer(...handlers);
```

`ui/src/test/setup.ts`:
```typescript
import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./server";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- src/test/smoke.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/test
git commit -m "test: vitest + msw harness"
```

## Task B3: API client (envelope unwrap + typed errors)

**Files:**
- Create: `ui/src/lib/api/client.ts`
- Test: `ui/src/lib/api/client.test.ts`

- [ ] **Step 1: Write the failing test**

`ui/src/lib/api/client.test.ts`:
```typescript
import { afterEach, expect, test } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { apiGet, apiPost, ApiError } from "./client";

afterEach(() => server.resetHandlers());

test("apiGet unwraps the data envelope", async () => {
  server.use(
    http.get("/api/ping", () =>
      HttpResponse.json({ success: true, data: { pong: 1 }, error: null }),
    ),
  );
  const data = await apiGet<{ pong: number }>("/ping");
  expect(data.pong).toBe(1);
});

test("apiGet throws ApiError with status and message on failure", async () => {
  server.use(
    http.get("/api/boom", () =>
      HttpResponse.json({ success: false, data: null, error: "nope" }, { status: 409 }),
    ),
  );
  await expect(apiGet("/boom")).rejects.toMatchObject({ status: 409, message: "nope" });
  await expect(apiGet("/boom")).rejects.toBeInstanceOf(ApiError);
});

test("apiPost returns unwrapped data and reads meta when asked", async () => {
  server.use(
    http.post("/api/things", () =>
      HttpResponse.json({ success: true, data: { id: "x" }, error: null }, { status: 201 }),
    ),
  );
  const data = await apiPost<{ id: string }>("/things", { name: "a" });
  expect(data.id).toBe("x");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- src/lib/api/client.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`ui/src/lib/api/client.ts`:
```typescript
const BASE = "/api";

export interface Envelope<T> {
  success: boolean;
  data: T | null;
  error: string | null;
  meta?: PageMeta;
}

export interface PageMeta {
  total: number;
  page_size: number;
  page_number: number;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<Envelope<T>> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  let body: Envelope<T>;
  try {
    body = (await res.json()) as Envelope<T>;
  } catch {
    throw new ApiError(res.status, res.statusText || "request failed");
  }
  if (!res.ok || !body.success) {
    throw new ApiError(res.status, body.error ?? res.statusText);
  }
  return body;
}

export async function apiGet<T>(path: string): Promise<T> {
  return (await request<T>(path)).data as T;
}

export async function apiGetPage<T>(path: string): Promise<{ data: T; meta?: PageMeta }> {
  const env = await request<T>(path);
  return { data: env.data as T, meta: env.meta };
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return (await request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }))
    .data as T;
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return (await request<T>(path, { method: "PATCH", body: JSON.stringify(body) })).data as T;
}

export async function apiDelete<T>(path: string): Promise<T> {
  return (await request<T>(path, { method: "DELETE" })).data as T;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- src/lib/api/client.test.ts`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add ui/src/lib/api/client.ts ui/src/lib/api/client.test.ts
git commit -m "feat: api client with envelope unwrap and typed errors"
```

## Task B4: Domain types

**Files:**
- Create: `ui/src/lib/api/types.ts`

- [ ] **Step 1: Create the types (no test — pure type declarations)**

`ui/src/lib/api/types.ts` (mirror `src/domain/models.py` enums/fields exactly):
```typescript
export type WorkItemKind = "epic" | "feature" | "task";

export type WorkItemStatus =
  | "draft"
  | "refining"
  | "ready"
  | "in_progress"
  | "in_review"
  | "approved"
  | "done"
  | "blocked"
  | "failed";

export type AutonomyLevel = "gated_all" | "gated_merge" | "full_auto";

export type RunStatus =
  | "pending"
  | "running"
  | "awaiting_approval"
  | "done"
  | "failed"
  | "blocked"
  | "cancelled";

export interface Project {
  id: string;
  owner_id: string;
  name: string;
  repo_url: string | null;
  local_path: string | null;
  team_id: string | null;
  autonomy: AutonomyLevel;
  created_at: string;
}

export interface WorkItem {
  id: string;
  project_id: string;
  owner_id: string;
  kind: WorkItemKind;
  parent_id: string | null;
  title: string;
  body: string;
  acceptance_criteria: string[];
  status: WorkItemStatus;
  created_at: string;
  updated_at: string;
}

export interface Run {
  id: string;
  owner_id: string;
  task_id: string;
  team_id: string;
  status: RunStatus;
  stage: string | null;
  branch: string | null;
  pr_url: string | null;
  cost_usd: number;
  created_at: string;
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd ui && npm run lint`
Expected: no type errors.

- [ ] **Step 3: Commit**

```bash
git add ui/src/lib/api/types.ts
git commit -m "feat: frontend domain types mirroring domain models"
```

## Task B5: App providers (QueryClient + Router) and routes shell

**Files:**
- Modify: `ui/src/app/App.tsx`, `ui/src/main.tsx`
- Create: `ui/src/app/router.tsx`, `ui/src/app/ErrorBoundary.tsx`, `ui/src/features/projects/ProjectsPage.tsx`, `ui/src/features/board/BoardPage.tsx`
- Test: `ui/src/app/router.test.tsx`

- [ ] **Step 1: Write the failing test**

`ui/src/app/router.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { AppProviders } from "./App";

test("renders the projects page at the root route", async () => {
  window.history.pushState({}, "", "/");
  render(<AppProviders />);
  expect(await screen.findByRole("heading", { name: /projects/i })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- src/app/router.test.tsx`
Expected: FAIL — `AppProviders` not exported.

- [ ] **Step 3: Implement providers, router, pages**

`ui/src/app/ErrorBoundary.tsx`:
```tsx
import { Component, type ReactNode } from "react";

export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    if (this.state.error) {
      return (
        <div className="p-6 text-red-600">
          Something went wrong: {this.state.error.message}
        </div>
      );
    }
    return this.props.children;
  }
}
```

`ui/src/features/projects/ProjectsPage.tsx`:
```tsx
export default function ProjectsPage() {
  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold">Projects</h1>
    </div>
  );
}
```

`ui/src/features/board/BoardPage.tsx`:
```tsx
import { useParams } from "react-router-dom";

export default function BoardPage() {
  const { projectId } = useParams();
  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold">Board</h1>
      <p className="text-sm text-gray-500">Project {projectId}</p>
    </div>
  );
}
```

`ui/src/app/router.tsx`:
```tsx
import { createBrowserRouter } from "react-router-dom";
import ProjectsPage from "../features/projects/ProjectsPage";
import BoardPage from "../features/board/BoardPage";

export const router = createBrowserRouter([
  { path: "/", element: <ProjectsPage /> },
  { path: "/projects/:projectId", element: <BoardPage /> },
]);
```

`ui/src/app/App.tsx`:
```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import { ErrorBoundary } from "./ErrorBoundary";
import { router } from "./router";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});

export function AppProviders() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ErrorBoundary>
  );
}

export default AppProviders;
```

`ui/src/main.tsx`:
```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { AppProviders } from "./app/App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AppProviders />
  </React.StrictMode>,
);
```

> Delete the old `ui/src/test/smoke.test.tsx` (it imported the removed default `App` shell), or update it to render `<AppProviders />`. Update it.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- src/app/router.test.tsx && npm run lint`
Expected: PASS, no type errors.

- [ ] **Step 5: Commit**

```bash
git add ui/src/app ui/src/main.tsx ui/src/features ui/src/test/smoke.test.tsx
git commit -m "feat: app providers, router, page shells"
```

---

# Part C — Projects feature

## Task C1: Projects API module + list query

**Files:**
- Create: `ui/src/lib/api/projects.ts`, `ui/src/features/projects/useProjects.ts`
- Test: `ui/src/features/projects/useProjects.test.tsx`

- [ ] **Step 1: Write the failing test**

`ui/src/features/projects/useProjects.test.tsx`:
```tsx
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { useProjects } from "./useProjects";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

test("useProjects returns the project list", async () => {
  server.use(
    http.get("/api/projects", () =>
      HttpResponse.json({
        success: true,
        data: [{ id: "p1", owner_id: "dev-user", name: "Alpha", repo_url: "x", local_path: null, team_id: null, autonomy: "gated_all", created_at: "2026-01-01T00:00:00Z" }],
        error: null,
        meta: { total: 1, page_size: 100, page_number: 1 },
      }),
    ),
  );
  const { result } = renderHook(() => useProjects(), { wrapper });
  await waitFor(() => expect(result.current.data).toHaveLength(1));
  expect(result.current.data![0].name).toBe("Alpha");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- src/features/projects/useProjects.test.tsx`
Expected: FAIL — modules missing.

- [ ] **Step 3: Implement**

`ui/src/lib/api/projects.ts`:
```typescript
import { apiGetPage, apiPost } from "./client";
import type { Project } from "./types";

export const projectKeys = {
  all: ["projects"] as const,
};

export interface CreateProjectInput {
  name: string;
  repo_url?: string;
  local_path?: string;
}

export async function listProjects(): Promise<Project[]> {
  const { data } = await apiGetPage<Project[]>("/projects?page_size=200");
  return data;
}

export async function createProject(input: CreateProjectInput): Promise<Project> {
  return apiPost<Project>("/projects", input);
}
```

`ui/src/features/projects/useProjects.ts`:
```typescript
import { useQuery } from "@tanstack/react-query";
import { listProjects, projectKeys } from "../../lib/api/projects";

export function useProjects() {
  return useQuery({ queryKey: projectKeys.all, queryFn: listProjects });
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- src/features/projects/useProjects.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/lib/api/projects.ts ui/src/features/projects/useProjects.ts ui/src/features/projects/useProjects.test.tsx
git commit -m "feat: projects api module + useProjects query"
```

## Task C2: Projects page list + create dialog

**Files:**
- Modify: `ui/src/features/projects/ProjectsPage.tsx`
- Create: `ui/src/features/projects/CreateProjectDialog.tsx`, `ui/src/features/projects/useCreateProject.ts`
- Test: `ui/src/features/projects/ProjectsPage.test.tsx`

- [ ] **Step 1: Write the failing test**

`ui/src/features/projects/ProjectsPage.test.tsx`:
```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import ProjectsPage from "./ProjectsPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("lists projects and creates a new one", async () => {
  const projects = [{ id: "p1", owner_id: "dev-user", name: "Alpha", repo_url: "x", local_path: null, team_id: null, autonomy: "gated_all", created_at: "2026-01-01T00:00:00Z" }];
  server.use(
    http.get("/api/projects", () =>
      HttpResponse.json({ success: true, data: projects, error: null, meta: { total: projects.length, page_size: 200, page_number: 1 } }),
    ),
    http.post("/api/projects", async ({ request }) => {
      const body = (await request.json()) as { name: string };
      const created = { id: "p2", owner_id: "dev-user", name: body.name, repo_url: "y", local_path: null, team_id: null, autonomy: "gated_all", created_at: "2026-01-02T00:00:00Z" };
      projects.push(created);
      return HttpResponse.json({ success: true, data: created, error: null }, { status: 201 });
    }),
  );

  renderPage();
  expect(await screen.findByText("Alpha")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: /new project/i }));
  await userEvent.type(screen.getByLabelText(/name/i), "Beta");
  await userEvent.type(screen.getByLabelText(/repo url/i), "y");
  await userEvent.click(screen.getByRole("button", { name: /^create$/i }));

  await waitFor(() => expect(screen.getByText("Beta")).toBeInTheDocument());
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- src/features/projects/ProjectsPage.test.tsx`
Expected: FAIL — no "New Project" button.

- [ ] **Step 3: Implement**

`ui/src/features/projects/useCreateProject.ts`:
```typescript
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createProject, projectKeys } from "../../lib/api/projects";

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createProject,
    onSuccess: () => qc.invalidateQueries({ queryKey: projectKeys.all }),
  });
}
```

`ui/src/features/projects/CreateProjectDialog.tsx`:
```tsx
import { useState } from "react";
import { useCreateProject } from "./useCreateProject";

export function CreateProjectDialog({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [localPath, setLocalPath] = useState("");
  const create = useCreateProject();

  const canSubmit = name.trim() !== "" && (repoUrl.trim() !== "" || localPath.trim() !== "");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    await create.mutateAsync({
      name,
      repo_url: repoUrl.trim() || undefined,
      local_path: localPath.trim() || undefined,
    });
    onClose();
  }

  return (
    <div className="fixed inset-0 grid place-items-center bg-black/30">
      <form onSubmit={submit} className="w-96 space-y-3 rounded bg-white p-4 shadow">
        <h2 className="text-lg font-semibold">New project</h2>
        <label className="block text-sm">
          Name
          <input className="mt-1 w-full rounded border p-2" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="block text-sm">
          Repo URL
          <input className="mt-1 w-full rounded border p-2" value={repoUrl} onChange={(e) => setRepoUrl(e.target.value)} />
        </label>
        <label className="block text-sm">
          Local path
          <input className="mt-1 w-full rounded border p-2" value={localPath} onChange={(e) => setLocalPath(e.target.value)} />
        </label>
        {!canSubmit && <p className="text-xs text-gray-500">Name and a repo URL or local path are required.</p>}
        {create.isError && <p className="text-xs text-red-600">{(create.error as Error).message}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded px-3 py-1 text-sm">Cancel</button>
          <button type="submit" disabled={!canSubmit || create.isPending} className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50">Create</button>
        </div>
      </form>
    </div>
  );
}
```

`ui/src/features/projects/ProjectsPage.tsx`:
```tsx
import { useState } from "react";
import { Link } from "react-router-dom";
import { useProjects } from "./useProjects";
import { CreateProjectDialog } from "./CreateProjectDialog";

export default function ProjectsPage() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const { data, isLoading, isError, error } = useProjects();

  return (
    <div className="p-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Projects</h1>
        <button onClick={() => setDialogOpen(true)} className="rounded bg-blue-600 px-3 py-1 text-sm text-white">
          New project
        </button>
      </div>
      {isLoading && <p className="text-sm text-gray-500">Loading…</p>}
      {isError && <p className="text-sm text-red-600">{(error as Error).message}</p>}
      <ul className="space-y-2">
        {data?.map((p) => (
          <li key={p.id} className="rounded border p-3">
            <Link to={`/projects/${p.id}`} className="font-medium text-blue-700">{p.name}</Link>
          </li>
        ))}
      </ul>
      {dialogOpen && <CreateProjectDialog onClose={() => setDialogOpen(false)} />}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- src/features/projects/ProjectsPage.test.tsx && npm run lint`
Expected: PASS, no type errors.

- [ ] **Step 5: Commit**

```bash
git add ui/src/features/projects
git commit -m "feat: projects list page + create dialog"
```

---

# Part D — Board, work-items, hierarchy

## Task D1: Work-items API module + column grouping (pure logic)

**Files:**
- Create: `ui/src/lib/api/workItems.ts`, `ui/src/features/board/columns.ts`
- Test: `ui/src/features/board/columns.test.ts`

- [ ] **Step 1: Write the failing test**

`ui/src/features/board/columns.test.ts`:
```typescript
import { describe, expect, test } from "vitest";
import { BOARD_COLUMNS, columnForStatus, groupByColumn, ATTENTION } from "./columns";
import type { WorkItem } from "../../lib/api/types";

function task(id: string, status: WorkItem["status"]): WorkItem {
  return {
    id, project_id: "p", owner_id: "u", kind: "task", parent_id: "f",
    title: id, body: "", acceptance_criteria: [], status,
    created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
  };
}

test("there are 7 flow columns plus the attention column", () => {
  expect(BOARD_COLUMNS).toHaveLength(8);
  expect(BOARD_COLUMNS[BOARD_COLUMNS.length - 1].id).toBe(ATTENTION);
});

test("blocked and failed map to the attention column", () => {
  expect(columnForStatus("blocked")).toBe(ATTENTION);
  expect(columnForStatus("failed")).toBe(ATTENTION);
});

test("flow statuses map to their own column", () => {
  expect(columnForStatus("ready")).toBe("ready");
  expect(columnForStatus("in_progress")).toBe("in_progress");
});

test("groupByColumn buckets tasks under the right columns", () => {
  const grouped = groupByColumn([task("a", "ready"), task("b", "failed"), task("c", "blocked")]);
  expect(grouped.ready.map((t) => t.id)).toEqual(["a"]);
  expect(grouped[ATTENTION].map((t) => t.id)).toEqual(["b", "c"]);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- src/features/board/columns.test.ts`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

`ui/src/features/board/columns.ts`:
```typescript
import type { WorkItem, WorkItemStatus } from "../../lib/api/types";

export const ATTENTION = "attention" as const;

export interface BoardColumn {
  id: string;
  title: string;
  /** statuses that live in this column; the first is the drop target status */
  statuses: WorkItemStatus[];
}

export const BOARD_COLUMNS: BoardColumn[] = [
  { id: "draft", title: "Draft", statuses: ["draft"] },
  { id: "refining", title: "Refining", statuses: ["refining"] },
  { id: "ready", title: "Ready", statuses: ["ready"] },
  { id: "in_progress", title: "In Progress", statuses: ["in_progress"] },
  { id: "in_review", title: "In Review", statuses: ["in_review"] },
  { id: "approved", title: "Approved", statuses: ["approved"] },
  { id: "done", title: "Done", statuses: ["done"] },
  { id: ATTENTION, title: "Attention", statuses: ["blocked", "failed"] },
];

const STATUS_TO_COLUMN: Record<WorkItemStatus, string> = Object.fromEntries(
  BOARD_COLUMNS.flatMap((c) => c.statuses.map((s) => [s, c.id])),
) as Record<WorkItemStatus, string>;

export function columnForStatus(status: WorkItemStatus): string {
  return STATUS_TO_COLUMN[status];
}

export function groupByColumn(items: WorkItem[]): Record<string, WorkItem[]> {
  const groups: Record<string, WorkItem[]> = {};
  for (const col of BOARD_COLUMNS) groups[col.id] = [];
  for (const item of items) groups[columnForStatus(item.status)].push(item);
  return groups;
}
```

`ui/src/lib/api/workItems.ts`:
```typescript
import { apiDelete, apiGetPage, apiPatch, apiPost } from "./client";
import type { WorkItem, WorkItemKind, WorkItemStatus } from "./types";

export const workItemKeys = {
  list: (projectId: string) => ["work-items", projectId] as const,
};

export interface WorkItemFilters {
  kind?: WorkItemKind;
  parent_id?: string;
}

export async function listWorkItems(
  projectId: string,
  filters: WorkItemFilters = {},
): Promise<WorkItem[]> {
  const params = new URLSearchParams({ page_size: "200" });
  if (filters.kind) params.set("kind", filters.kind);
  if (filters.parent_id) params.set("parent_id", filters.parent_id);
  const { data } = await apiGetPage<WorkItem[]>(`/projects/${projectId}/work-items?${params}`);
  return data;
}

export interface CreateWorkItemInput {
  kind: WorkItemKind;
  title: string;
  body?: string;
  parent_id?: string;
  acceptance_criteria?: string[];
}

export async function createWorkItem(projectId: string, input: CreateWorkItemInput): Promise<WorkItem> {
  return apiPost<WorkItem>(`/projects/${projectId}/work-items`, input);
}

export interface UpdateWorkItemInput {
  title?: string;
  body?: string;
  acceptance_criteria?: string[];
}

export async function updateWorkItem(itemId: string, input: UpdateWorkItemInput): Promise<WorkItem> {
  return apiPatch<WorkItem>(`/work-items/${itemId}`, input);
}

export async function setWorkItemStatus(itemId: string, status: WorkItemStatus): Promise<WorkItem> {
  return apiPost<WorkItem>(`/work-items/${itemId}/status`, { status });
}

export async function deleteWorkItem(itemId: string): Promise<void> {
  await apiDelete(`/work-items/${itemId}`);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- src/features/board/columns.test.ts && npm run lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/lib/api/workItems.ts ui/src/features/board/columns.ts ui/src/features/board/columns.test.ts
git commit -m "feat: work-items api module + board column grouping"
```

## Task D2: Optimistic status mutation hook (with rollback)

**Files:**
- Create: `ui/src/features/board/useSetStatus.ts`
- Test: `ui/src/features/board/useSetStatus.test.tsx`

- [ ] **Step 1: Write the failing test**

`ui/src/features/board/useSetStatus.test.tsx`:
```tsx
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { workItemKeys } from "../../lib/api/workItems";
import { useSetStatus } from "./useSetStatus";
import type { WorkItem } from "../../lib/api/types";

const PROJECT = "p1";
function task(id: string, status: WorkItem["status"]): WorkItem {
  return { id, project_id: PROJECT, owner_id: "u", kind: "task", parent_id: "f", title: id, body: "", acceptance_criteria: [], status, created_at: "x", updated_at: "x" };
}

function makeWrapper(qc: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

test("rolls back the cached status when the API returns 409", async () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(workItemKeys.list(PROJECT), [task("a", "ready")]);
  server.use(
    http.post("/api/work-items/a/status", () =>
      HttpResponse.json({ success: false, data: null, error: "bad transition" }, { status: 409 }),
    ),
  );

  const { result } = renderHook(() => useSetStatus(PROJECT), { wrapper: makeWrapper(qc) });
  result.current.mutate({ itemId: "a", status: "done" });

  await waitFor(() => expect(result.current.isError).toBe(true));
  const cached = qc.getQueryData<WorkItem[]>(workItemKeys.list(PROJECT))!;
  expect(cached[0].status).toBe("ready"); // rolled back
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- src/features/board/useSetStatus.test.tsx`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

`ui/src/features/board/useSetStatus.ts`:
```typescript
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { setWorkItemStatus, workItemKeys } from "../../lib/api/workItems";
import type { WorkItem, WorkItemStatus } from "../../lib/api/types";

interface Vars {
  itemId: string;
  status: WorkItemStatus;
}

export function useSetStatus(projectId: string) {
  const qc = useQueryClient();
  const key = workItemKeys.list(projectId);
  return useMutation({
    mutationFn: ({ itemId, status }: Vars) => setWorkItemStatus(itemId, status),
    onMutate: async ({ itemId, status }) => {
      await qc.cancelQueries({ queryKey: key });
      const previous = qc.getQueryData<WorkItem[]>(key);
      qc.setQueryData<WorkItem[]>(key, (old) =>
        (old ?? []).map((i) => (i.id === itemId ? { ...i, status } : i)),
      );
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) qc.setQueryData(key, ctx.previous);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- src/features/board/useSetStatus.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/features/board/useSetStatus.ts ui/src/features/board/useSetStatus.test.tsx
git commit -m "feat: optimistic status mutation with rollback"
```

## Task D3: Board with dnd-kit columns and cards

**Files:**
- Create: `ui/src/features/board/useBoardItems.ts`, `ui/src/features/board/TaskCard.tsx`, `ui/src/features/board/Column.tsx`, `ui/src/features/board/Board.tsx`
- Modify: `ui/src/features/board/BoardPage.tsx`
- Test: `ui/src/features/board/Board.test.tsx`

- [ ] **Step 1: Write the failing test**

`ui/src/features/board/Board.test.tsx`:
```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { Board } from "./Board";

function renderBoard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Board projectId="p1" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("renders columns and places tasks by status", async () => {
  server.use(
    http.get("/api/projects/p1/work-items", () =>
      HttpResponse.json({
        success: true,
        data: [
          { id: "t1", project_id: "p1", owner_id: "u", kind: "task", parent_id: "f", title: "Build login", body: "", acceptance_criteria: [], status: "ready", created_at: "x", updated_at: "x" },
          { id: "t2", project_id: "p1", owner_id: "u", kind: "task", parent_id: "f", title: "Broken thing", body: "", acceptance_criteria: [], status: "failed", created_at: "x", updated_at: "x" },
        ],
        error: null,
        meta: { total: 2, page_size: 200, page_number: 1 },
      }),
    ),
  );
  renderBoard();
  expect(await screen.findByText("Build login")).toBeInTheDocument();
  expect(screen.getByText("Broken thing")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: /attention/i })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- src/features/board/Board.test.tsx`
Expected: FAIL — `Board` missing.

- [ ] **Step 3: Implement**

`ui/src/features/board/useBoardItems.ts`:
```typescript
import { useQuery } from "@tanstack/react-query";
import { listWorkItems, workItemKeys, type WorkItemFilters } from "../../lib/api/workItems";

export function useBoardItems(projectId: string, parentId?: string) {
  const filters: WorkItemFilters = { kind: "task", parent_id: parentId };
  return useQuery({
    queryKey: parentId
      ? [...workItemKeys.list(projectId), "feature", parentId]
      : workItemKeys.list(projectId),
    queryFn: () => listWorkItems(projectId, filters),
  });
}
```

> Note: the optimistic mutation in Task D2 writes to `workItemKeys.list(projectId)`. To keep the board cache key stable and rollback correct, the board with no feature filter MUST use exactly `workItemKeys.list(projectId)` — which the `parentId ? ... : workItemKeys.list(projectId)` branch guarantees. The feature-filtered view uses its own key and re-fetches on settle.

`ui/src/features/board/TaskCard.tsx`:
```tsx
import { useDraggable } from "@dnd-kit/core";
import type { WorkItem } from "../../lib/api/types";

const ATTENTION_STATUSES = new Set(["blocked", "failed"]);

export function TaskCard({ item, onOpen }: { item: WorkItem; onOpen: (id: string) => void }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: item.id });
  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` }
    : undefined;
  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`mb-2 rounded border bg-white p-2 text-sm shadow-sm ${isDragging ? "opacity-50" : ""}`}
      {...listeners}
      {...attributes}
    >
      <button className="text-left font-medium" onClick={() => onOpen(item.id)}>
        {item.title}
      </button>
      {ATTENTION_STATUSES.has(item.status) && (
        <span className="ml-2 rounded bg-red-100 px-1.5 py-0.5 text-xs text-red-700">
          {item.status}
        </span>
      )}
    </div>
  );
}
```

`ui/src/features/board/Column.tsx`:
```tsx
import { useDroppable } from "@dnd-kit/core";
import type { BoardColumn } from "./columns";
import type { WorkItem } from "../../lib/api/types";
import { TaskCard } from "./TaskCard";

export function Column({
  column,
  items,
  onOpen,
}: {
  column: BoardColumn;
  items: WorkItem[];
  onOpen: (id: string) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: column.id });
  return (
    <div
      ref={setNodeRef}
      className={`flex w-56 shrink-0 flex-col rounded bg-gray-50 p-2 ${isOver ? "ring-2 ring-blue-400" : ""}`}
    >
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
        {column.title}
      </h2>
      {items.map((item) => (
        <TaskCard key={item.id} item={item} onOpen={onOpen} />
      ))}
    </div>
  );
}
```

`ui/src/features/board/Board.tsx`:
```tsx
import { DndContext, type DragEndEvent, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { BOARD_COLUMNS, columnForStatus, groupByColumn } from "./columns";
import { useBoardItems } from "./useBoardItems";
import { useSetStatus } from "./useSetStatus";
import { Column } from "./Column";
import type { WorkItemStatus } from "../../lib/api/types";

export function Board({ projectId, parentId, onOpen }: { projectId: string; parentId?: string; onOpen?: (id: string) => void }) {
  const { data, isLoading, isError, error } = useBoardItems(projectId, parentId);
  const setStatus = useSetStatus(projectId);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  function onDragEnd(e: DragEndEvent) {
    const itemId = String(e.active.id);
    const columnId = e.over ? String(e.over.id) : null;
    if (!columnId || !data) return;
    const item = data.find((i) => i.id === itemId);
    if (!item) return;
    const column = BOARD_COLUMNS.find((c) => c.id === columnId);
    if (!column) return;
    const target = column.statuses[0] as WorkItemStatus; // first status is the drop target
    if (target === item.status || columnForStatus(item.status) === columnId) return;
    setStatus.mutate({ itemId, status: target });
  }

  if (isLoading) return <p className="p-4 text-sm text-gray-500">Loading board…</p>;
  if (isError) return <p className="p-4 text-sm text-red-600">{(error as Error).message}</p>;

  const grouped = groupByColumn(data ?? []);
  return (
    <DndContext sensors={sensors} onDragEnd={onDragEnd}>
      <div className="flex gap-3 overflow-x-auto p-4">
        {BOARD_COLUMNS.map((column) => (
          <Column key={column.id} column={column} items={grouped[column.id]} onOpen={onOpen ?? (() => {})} />
        ))}
      </div>
      {setStatus.isError && (
        <p className="px-4 text-sm text-red-600">Move rejected: {(setStatus.error as Error).message}</p>
      )}
    </DndContext>
  );
}
```

`ui/src/features/board/BoardPage.tsx`:
```tsx
import { useParams, useSearchParams, Link } from "react-router-dom";
import { Board } from "./Board";

export default function BoardPage() {
  const { projectId } = useParams();
  const [params, setParams] = useSearchParams();
  if (!projectId) return null;

  const openItem = (id: string) => {
    params.set("item", id);
    setParams(params);
  };

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center gap-3 border-b p-3">
        <Link to="/" className="text-sm text-blue-700">← Projects</Link>
        <h1 className="font-semibold">Board</h1>
      </header>
      <Board projectId={projectId} onOpen={openItem} />
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- src/features/board/Board.test.tsx && npm run lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/features/board
git commit -m "feat: dnd-kit kanban board with optimistic transitions"
```

## Task D4: Ticket slide-over panel (details + acceptance criteria)

**Files:**
- Create: `ui/src/lib/api/workItemDetail.ts`, `ui/src/features/work-items/useWorkItem.ts`, `ui/src/features/work-items/useUpdateWorkItem.ts`, `ui/src/features/work-items/TicketPanel.tsx`, `ui/src/features/work-items/AcceptanceCriteria.tsx`
- Modify: `ui/src/features/board/BoardPage.tsx`
- Test: `ui/src/features/work-items/TicketPanel.test.tsx`

- [ ] **Step 1: Write the failing test**

`ui/src/features/work-items/TicketPanel.test.tsx`:
```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { TicketPanel } from "./TicketPanel";

const item = { id: "t1", project_id: "p1", owner_id: "u", kind: "task", parent_id: "f", title: "Build login", body: "do it", acceptance_criteria: ["AC1"], status: "ready", created_at: "x", updated_at: "x" };

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TicketPanel projectId="p1" itemId="t1" onClose={() => {}} />
    </QueryClientProvider>,
  );
}

test("shows the ticket and saves an edited acceptance criterion", async () => {
  let current = { ...item };
  server.use(
    http.get("/api/work-items/t1", () => HttpResponse.json({ success: true, data: current, error: null })),
    http.patch("/api/work-items/t1", async ({ request }) => {
      const body = (await request.json()) as { acceptance_criteria?: string[] };
      current = { ...current, ...body };
      return HttpResponse.json({ success: true, data: current, error: null });
    }),
    http.get("/api/work-items/t1/runs", () => HttpResponse.json({ success: true, data: [], error: null, meta: { total: 0, page_size: 100, page_number: 1 } })),
  );

  renderPanel();
  expect(await screen.findByDisplayValue("Build login")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /add criterion/i }));
  const inputs = screen.getAllByPlaceholderText(/criterion/i);
  await userEvent.type(inputs[inputs.length - 1], "AC2");
  await userEvent.click(screen.getByRole("button", { name: /save/i }));
  await waitFor(() => expect(current.acceptance_criteria).toContain("AC2"));
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- src/features/work-items/TicketPanel.test.tsx`
Expected: FAIL — modules missing.

- [ ] **Step 3: Implement**

`ui/src/lib/api/workItemDetail.ts`:
```typescript
import { apiGet } from "./client";
import type { WorkItem } from "./types";

export const workItemDetailKey = (id: string) => ["work-item", id] as const;

export async function getWorkItem(itemId: string): Promise<WorkItem> {
  return apiGet<WorkItem>(`/work-items/${itemId}`);
}
```

> Backend note: this consumes the `GET /work-items/{id}` route added in **Task A5**. A5 must be done before D4.

`ui/src/features/work-items/useWorkItem.ts`:
```typescript
import { useQuery } from "@tanstack/react-query";
import { getWorkItem, workItemDetailKey } from "../../lib/api/workItemDetail";

export function useWorkItem(itemId: string) {
  return useQuery({ queryKey: workItemDetailKey(itemId), queryFn: () => getWorkItem(itemId) });
}
```

`ui/src/features/work-items/useUpdateWorkItem.ts`:
```typescript
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateWorkItem, workItemKeys, type UpdateWorkItemInput } from "../../lib/api/workItems";
import { workItemDetailKey } from "../../lib/api/workItemDetail";

export function useUpdateWorkItem(projectId: string, itemId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: UpdateWorkItemInput) => updateWorkItem(itemId, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: workItemDetailKey(itemId) });
      qc.invalidateQueries({ queryKey: workItemKeys.list(projectId) });
    },
  });
}
```

`ui/src/features/work-items/AcceptanceCriteria.tsx`:
```tsx
export function AcceptanceCriteria({
  value,
  onChange,
}: {
  value: string[];
  onChange: (next: string[]) => void;
}) {
  return (
    <div className="space-y-2">
      {value.map((c, i) => (
        <div key={i} className="flex gap-2">
          <input
            className="w-full rounded border p-1 text-sm"
            placeholder="criterion"
            value={c}
            onChange={(e) => onChange(value.map((v, j) => (j === i ? e.target.value : v)))}
          />
          <button
            type="button"
            className="text-sm text-red-600"
            onClick={() => onChange(value.filter((_, j) => j !== i))}
          >
            ×
          </button>
        </div>
      ))}
      <button type="button" className="text-sm text-blue-700" onClick={() => onChange([...value, ""])}>
        Add criterion
      </button>
    </div>
  );
}
```

`ui/src/features/work-items/TicketPanel.tsx`:
```tsx
import { useEffect, useState } from "react";
import { useWorkItem } from "./useWorkItem";
import { useUpdateWorkItem } from "./useUpdateWorkItem";
import { AcceptanceCriteria } from "./AcceptanceCriteria";
import { RunSection } from "../runs/RunSection";

export function TicketPanel({
  projectId,
  itemId,
  onClose,
}: {
  projectId: string;
  itemId: string;
  onClose: () => void;
}) {
  const { data, isLoading, isError, error } = useWorkItem(itemId);
  const update = useUpdateWorkItem(projectId, itemId);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [criteria, setCriteria] = useState<string[]>([]);

  useEffect(() => {
    if (data) {
      setTitle(data.title);
      setBody(data.body);
      setCriteria(data.acceptance_criteria);
    }
  }, [data]);

  return (
    <aside className="fixed right-0 top-0 h-screen w-[28rem] overflow-y-auto border-l bg-white p-4 shadow-xl">
      <div className="mb-3 flex justify-between">
        <h2 className="font-semibold">Ticket</h2>
        <button onClick={onClose} className="text-sm text-gray-500">Close</button>
      </div>
      {isLoading && <p className="text-sm text-gray-500">Loading…</p>}
      {isError && <p className="text-sm text-red-600">{(error as Error).message}</p>}
      {data && (
        <div className="space-y-4">
          <input className="w-full rounded border p-2 text-sm font-medium" value={title} onChange={(e) => setTitle(e.target.value)} />
          <textarea className="h-28 w-full rounded border p-2 text-sm" value={body} onChange={(e) => setBody(e.target.value)} />
          <div>
            <h3 className="mb-1 text-xs font-semibold uppercase text-gray-500">Acceptance criteria</h3>
            <AcceptanceCriteria value={criteria} onChange={setCriteria} />
          </div>
          {update.isError && <p className="text-sm text-red-600">{(update.error as Error).message}</p>}
          <button
            className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50"
            disabled={update.isPending}
            onClick={() => update.mutate({ title, body, acceptance_criteria: criteria })}
          >
            Save
          </button>
          <RunSection projectId={projectId} taskId={itemId} taskStatus={data.status} />
        </div>
      )}
    </aside>
  );
}
```

> `RunSection` is created in Task D5. To keep this task's test green before D5 exists, create a temporary stub `ui/src/features/runs/RunSection.tsx` exporting `export function RunSection() { return null; }`, then flesh it out in D5. The MSW handler for `/work-items/t1/runs` in this test covers the eventual fetch.

Wire the panel into the board: in `ui/src/features/board/BoardPage.tsx`, read `item` from search params and render the panel:
```tsx
// add inside BoardPage, after <Board .../>:
{params.get("item") && (
  <TicketPanel
    projectId={projectId}
    itemId={params.get("item")!}
    onClose={() => { params.delete("item"); setParams(params); }}
  />
)}
```
(Add `import { TicketPanel } from "../work-items/TicketPanel";` at the top of `BoardPage.tsx`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- src/features/work-items/TicketPanel.test.tsx && npm run lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/lib/api/workItemDetail.ts ui/src/features/work-items ui/src/features/runs/RunSection.tsx ui/src/features/board/BoardPage.tsx
git commit -m "feat: ticket slide-over with details + acceptance criteria"
```

## Task D5: Hierarchy tree (epic/feature/task CRUD + feature filter)

**Files:**
- Create: `ui/src/features/work-items/useHierarchy.ts`, `ui/src/features/work-items/HierarchyTree.tsx`, `ui/src/features/work-items/useCreateWorkItem.ts`, `ui/src/features/work-items/useDeleteWorkItem.ts`
- Modify: `ui/src/features/board/BoardPage.tsx`
- Test: `ui/src/features/work-items/HierarchyTree.test.tsx`

- [ ] **Step 1: Write the failing test**

`ui/src/features/work-items/HierarchyTree.test.tsx`:
```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { HierarchyTree } from "./HierarchyTree";

function renderTree(onSelectFeature = () => {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <HierarchyTree projectId="p1" selectedFeature={undefined} onSelectFeature={onSelectFeature} />
    </QueryClientProvider>,
  );
}

test("lists epics and features and creates an epic", async () => {
  const items: any[] = [
    { id: "e1", project_id: "p1", owner_id: "u", kind: "epic", parent_id: null, title: "Epic One", body: "", acceptance_criteria: [], status: "draft", created_at: "x", updated_at: "x" },
  ];
  server.use(
    http.get("/api/projects/p1/work-items", ({ request }) => {
      const url = new URL(request.url);
      const kind = url.searchParams.get("kind");
      const data = kind ? items.filter((i) => i.kind === kind) : items;
      return HttpResponse.json({ success: true, data, error: null, meta: { total: data.length, page_size: 200, page_number: 1 } });
    }),
    http.post("/api/projects/p1/work-items", async ({ request }) => {
      const body = (await request.json()) as { title: string; kind: string };
      const created = { id: "e2", project_id: "p1", owner_id: "u", kind: body.kind, parent_id: null, title: body.title, body: "", acceptance_criteria: [], status: "draft", created_at: "x", updated_at: "x" };
      items.push(created);
      return HttpResponse.json({ success: true, data: created, error: null }, { status: 201 });
    }),
  );

  renderTree();
  expect(await screen.findByText("Epic One")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /add epic/i }));
  await userEvent.type(screen.getByPlaceholderText(/new epic title/i), "Epic Two");
  await userEvent.click(screen.getByRole("button", { name: /^create$/i }));
  await waitFor(() => expect(screen.getByText("Epic Two")).toBeInTheDocument());
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- src/features/work-items/HierarchyTree.test.tsx`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

`ui/src/features/work-items/useHierarchy.ts`:
```typescript
import { useQuery } from "@tanstack/react-query";
import { listWorkItems } from "../../lib/api/workItems";
import type { WorkItem } from "../../lib/api/types";

export function useEpics(projectId: string) {
  return useQuery<WorkItem[]>({
    queryKey: ["hierarchy", projectId, "epic"],
    queryFn: () => listWorkItems(projectId, { kind: "epic" }),
  });
}

export function useFeatures(projectId: string) {
  return useQuery<WorkItem[]>({
    queryKey: ["hierarchy", projectId, "feature"],
    queryFn: () => listWorkItems(projectId, { kind: "feature" }),
  });
}
```

`ui/src/features/work-items/useCreateWorkItem.ts`:
```typescript
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createWorkItem, workItemKeys, type CreateWorkItemInput } from "../../lib/api/workItems";

export function useCreateWorkItem(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateWorkItemInput) => createWorkItem(projectId, input),
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["hierarchy", projectId, created.kind] });
      qc.invalidateQueries({ queryKey: workItemKeys.list(projectId) });
    },
  });
}
```

`ui/src/features/work-items/useDeleteWorkItem.ts`:
```typescript
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteWorkItem, workItemKeys } from "../../lib/api/workItems";

export function useDeleteWorkItem(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (itemId: string) => deleteWorkItem(itemId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["hierarchy", projectId] });
      qc.invalidateQueries({ queryKey: workItemKeys.list(projectId) });
    },
  });
}
```

`ui/src/features/work-items/HierarchyTree.tsx`:
```tsx
import { useState } from "react";
import { useEpics, useFeatures } from "./useHierarchy";
import { useCreateWorkItem } from "./useCreateWorkItem";

export function HierarchyTree({
  projectId,
  selectedFeature,
  onSelectFeature,
}: {
  projectId: string;
  selectedFeature: string | undefined;
  onSelectFeature: (featureId: string | undefined) => void;
}) {
  const epics = useEpics(projectId);
  const features = useFeatures(projectId);
  const create = useCreateWorkItem(projectId);
  const [adding, setAdding] = useState<null | "epic" | "feature">(null);
  const [title, setTitle] = useState("");
  const [parentId, setParentId] = useState<string>("");

  async function submit() {
    if (!title.trim()) return;
    if (adding === "feature" && !parentId) return;
    await create.mutateAsync({
      kind: adding!,
      title,
      parent_id: adding === "feature" ? parentId : undefined,
    });
    setTitle("");
    setAdding(null);
  }

  return (
    <div className="w-60 shrink-0 border-r p-3 text-sm">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-semibold">Hierarchy</span>
      </div>
      <button className="mb-2 block text-left text-xs text-blue-700" onClick={() => onSelectFeature(undefined)}>
        All tasks
      </button>
      <ul className="space-y-1">
        {epics.data?.map((epic) => (
          <li key={epic.id}>
            <span className="font-medium">{epic.title}</span>
            <ul className="ml-3 mt-1 space-y-1">
              {features.data
                ?.filter((f) => f.parent_id === epic.id)
                .map((f) => (
                  <li key={f.id}>
                    <button
                      className={`text-left ${selectedFeature === f.id ? "text-blue-700 underline" : ""}`}
                      onClick={() => onSelectFeature(f.id)}
                    >
                      {f.title}
                    </button>
                  </li>
                ))}
            </ul>
          </li>
        ))}
      </ul>

      <div className="mt-3 space-y-1">
        <button className="block text-xs text-blue-700" onClick={() => setAdding("epic")}>+ Add epic</button>
        <button className="block text-xs text-blue-700" onClick={() => setAdding("feature")}>+ Add feature</button>
      </div>

      {adding && (
        <div className="mt-2 space-y-2 rounded border p-2">
          {adding === "feature" && (
            <select className="w-full rounded border p-1" value={parentId} onChange={(e) => setParentId(e.target.value)}>
              <option value="">Select epic…</option>
              {epics.data?.map((e) => (
                <option key={e.id} value={e.id}>{e.title}</option>
              ))}
            </select>
          )}
          <input
            className="w-full rounded border p-1"
            placeholder={adding === "epic" ? "New epic title" : "New feature title"}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <div className="flex gap-2">
            <button className="rounded bg-blue-600 px-2 py-0.5 text-xs text-white" onClick={submit}>Create</button>
            <button className="text-xs" onClick={() => setAdding(null)}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  );
}
```

Wire into `BoardPage.tsx`: render `<HierarchyTree>` beside `<Board>`, mapping the selected feature to the `feature` search param and passing it as `parentId` to `<Board>`:
```tsx
// BoardPage body becomes a flex row of tree + board:
const selectedFeature = params.get("feature") ?? undefined;
const selectFeature = (id: string | undefined) => {
  if (id) params.set("feature", id); else params.delete("feature");
  setParams(params);
};
// ...
<div className="flex flex-1 overflow-hidden">
  <HierarchyTree projectId={projectId} selectedFeature={selectedFeature} onSelectFeature={selectFeature} />
  <div className="flex-1 overflow-auto">
    <Board projectId={projectId} parentId={selectedFeature} onOpen={openItem} />
  </div>
</div>
```
(Add `import { HierarchyTree } from "../work-items/HierarchyTree";`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- src/features/work-items/HierarchyTree.test.tsx && npm run lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/features/work-items ui/src/features/board/BoardPage.tsx
git commit -m "feat: hierarchy tree (epic/feature CRUD + feature filter)"
```

---

# Part E — Runs UI

## Task E1: Runs API module + run section (list + start)

**Files:**
- Create: `ui/src/lib/api/runs.ts`, `ui/src/features/runs/useRuns.ts`, `ui/src/features/runs/useStartRun.ts`, `ui/src/features/runs/RunStatusBadge.tsx`
- Replace stub: `ui/src/features/runs/RunSection.tsx`
- Test: `ui/src/features/runs/RunSection.test.tsx`

- [ ] **Step 1: Write the failing test**

`ui/src/features/runs/RunSection.test.tsx`:
```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { RunSection } from "./RunSection";

function renderSection(taskStatus = "ready") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RunSection projectId="p1" taskId="t1" taskStatus={taskStatus} />
    </QueryClientProvider>,
  );
}

test("lists runs and starts a new one", async () => {
  const runs: any[] = [];
  server.use(
    http.get("/api/work-items/t1/runs", () =>
      HttpResponse.json({ success: true, data: runs, error: null, meta: { total: runs.length, page_size: 100, page_number: 1 } }),
    ),
    http.post("/api/work-items/t1/runs", () => {
      const run = { id: "r1", owner_id: "u", task_id: "t1", team_id: "tm", status: "pending", stage: null, branch: null, pr_url: null, cost_usd: 0, created_at: "x" };
      runs.push(run);
      return HttpResponse.json({ success: true, data: run, error: null }, { status: 201 });
    }),
  );

  renderSection();
  await userEvent.click(await screen.findByRole("button", { name: /^run$/i }));
  await waitFor(() => expect(screen.getByText(/pending/i)).toBeInTheDocument());
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- src/features/runs/RunSection.test.tsx`
Expected: FAIL — stub renders null.

- [ ] **Step 3: Implement**

`ui/src/lib/api/runs.ts`:
```typescript
import { apiGetPage, apiPatch, apiPost } from "./client";
import type { Run } from "./types";

export const runKeys = {
  forTask: (taskId: string) => ["runs", taskId] as const,
};

export async function listRuns(taskId: string): Promise<Run[]> {
  const { data } = await apiGetPage<Run[]>(`/work-items/${taskId}/runs?page_size=100`);
  return data;
}

export async function startRun(taskId: string): Promise<Run> {
  return apiPost<Run>(`/work-items/${taskId}/runs`);
}

export async function cancelRun(runId: string): Promise<Run> {
  return apiPost<Run>(`/runs/${runId}/cancel`);
}

export async function approveRun(runId: string): Promise<Run> {
  return apiPost<Run>(`/runs/${runId}/approve`);
}

export async function rejectRun(runId: string): Promise<Run> {
  return apiPost<Run>(`/runs/${runId}/reject`);
}

export interface UpdateRunInput {
  stage?: string;
  branch?: string;
  pr_url?: string;
}

export async function updateRun(runId: string, input: UpdateRunInput): Promise<Run> {
  return apiPatch<Run>(`/runs/${runId}`, input);
}
```

`ui/src/features/runs/useRuns.ts`:
```typescript
import { useQuery } from "@tanstack/react-query";
import { listRuns, runKeys } from "../../lib/api/runs";

export function useRuns(taskId: string) {
  return useQuery({ queryKey: runKeys.forTask(taskId), queryFn: () => listRuns(taskId) });
}
```

`ui/src/features/runs/useStartRun.ts`:
```typescript
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { runKeys, startRun } from "../../lib/api/runs";
import { workItemKeys } from "../../lib/api/workItems";

export function useStartRun(projectId: string, taskId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => startRun(taskId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: runKeys.forTask(taskId) });
      qc.invalidateQueries({ queryKey: workItemKeys.list(projectId) }); // start moves task to in_progress
    },
  });
}
```

`ui/src/features/runs/RunStatusBadge.tsx`:
```tsx
import type { RunStatus } from "../../lib/api/types";

const COLORS: Record<RunStatus, string> = {
  pending: "bg-gray-100 text-gray-700",
  running: "bg-blue-100 text-blue-700",
  awaiting_approval: "bg-amber-100 text-amber-800",
  done: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
  blocked: "bg-orange-100 text-orange-700",
  cancelled: "bg-gray-200 text-gray-600",
};

export function RunStatusBadge({ status }: { status: RunStatus }) {
  return <span className={`rounded px-1.5 py-0.5 text-xs ${COLORS[status]}`}>{status}</span>;
}
```

`ui/src/features/runs/RunSection.tsx` (replace stub):
```tsx
import { useRuns } from "./useRuns";
import { useStartRun } from "./useStartRun";
import { RunStatusBadge } from "./RunStatusBadge";
import { RunActions } from "./RunActions";
import type { WorkItemStatus } from "../../lib/api/types";

export function RunSection({
  projectId,
  taskId,
  taskStatus,
}: {
  projectId: string;
  taskId: string;
  taskStatus: WorkItemStatus;
}) {
  const { data, isLoading } = useRuns(taskId);
  const start = useStartRun(projectId, taskId);

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase text-gray-500">Runs</h3>
        <button
          className="rounded bg-emerald-600 px-3 py-1 text-sm text-white disabled:opacity-50"
          disabled={taskStatus !== "ready" || start.isPending}
          title={taskStatus !== "ready" ? "Task must be Ready to run" : undefined}
          onClick={() => start.mutate()}
        >
          Run
        </button>
      </div>
      {start.isError && <p className="text-sm text-red-600">{(start.error as Error).message}</p>}
      {isLoading && <p className="text-sm text-gray-500">Loading runs…</p>}
      <ul className="space-y-2">
        {data?.map((run) => (
          <li key={run.id} className="rounded border p-2 text-sm">
            <div className="flex items-center justify-between">
              <RunStatusBadge status={run.status} />
              <span className="text-xs text-gray-500">{run.stage ?? "—"}</span>
            </div>
            <RunActions taskId={taskId} run={run} />
          </li>
        ))}
      </ul>
    </div>
  );
}
```

> `RunActions` is built in Task E2. Create a temporary stub `ui/src/features/runs/RunActions.tsx` exporting `export function RunActions() { return null; }` so this task compiles; E2 replaces it.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- src/features/runs/RunSection.test.tsx && npm run lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/lib/api/runs.ts ui/src/features/runs
git commit -m "feat: runs api module + run list/start section"
```

## Task E2: Run actions (cancel / approve / reject / edit)

**Files:**
- Replace stub: `ui/src/features/runs/RunActions.tsx`
- Create: `ui/src/features/runs/useRunActions.ts`
- Test: `ui/src/features/runs/RunActions.test.tsx`

- [ ] **Step 1: Write the failing test**

`ui/src/features/runs/RunActions.test.tsx`:
```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { RunActions } from "./RunActions";
import type { Run } from "../../lib/api/types";

function run(status: Run["status"]): Run {
  return { id: "r1", owner_id: "u", task_id: "t1", team_id: "tm", status, stage: null, branch: null, pr_url: null, cost_usd: 0, created_at: "x" };
}

function renderActions(r: Run) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RunActions taskId="t1" run={r} />
    </QueryClientProvider>,
  );
}

test("approve and reject show only for awaiting_approval runs", () => {
  const { unmount } = renderActions(run("pending"));
  expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
  unmount();
  renderActions(run("awaiting_approval"));
  expect(screen.getByRole("button", { name: /approve/i })).toBeInTheDocument();
});

test("cancel calls the cancel endpoint", async () => {
  let cancelled = false;
  server.use(
    http.post("/api/runs/r1/cancel", () => {
      cancelled = true;
      return HttpResponse.json({ success: true, data: run("cancelled"), error: null });
    }),
  );
  renderActions(run("pending"));
  await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
  await waitFor(() => expect(cancelled).toBe(true));
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- src/features/runs/RunActions.test.tsx`
Expected: FAIL — stub renders null.

- [ ] **Step 3: Implement**

`ui/src/features/runs/useRunActions.ts`:
```typescript
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  approveRun,
  cancelRun,
  rejectRun,
  runKeys,
  updateRun,
  type UpdateRunInput,
} from "../../lib/api/runs";

export function useRunActions(taskId: string, runId: string) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: runKeys.forTask(taskId) });

  const cancel = useMutation({ mutationFn: () => cancelRun(runId), onSuccess: invalidate });
  const approve = useMutation({ mutationFn: () => approveRun(runId), onSuccess: invalidate });
  const reject = useMutation({ mutationFn: () => rejectRun(runId), onSuccess: invalidate });
  const edit = useMutation({
    mutationFn: (input: UpdateRunInput) => updateRun(runId, input),
    onSuccess: invalidate,
  });
  return { cancel, approve, reject, edit };
}
```

`ui/src/features/runs/RunActions.tsx` (replace stub):
```tsx
import { useState } from "react";
import type { Run } from "../../lib/api/types";
import { useRunActions } from "./useRunActions";

const TERMINAL = new Set(["done", "failed", "cancelled"]);

export function RunActions({ taskId, run }: { taskId: string; run: Run }) {
  const { cancel, approve, reject, edit } = useRunActions(taskId, run.id);
  const [editing, setEditing] = useState(false);
  const [branch, setBranch] = useState(run.branch ?? "");
  const [stage, setStage] = useState(run.stage ?? "");

  const isTerminal = TERMINAL.has(run.status);
  const isGate = run.status === "awaiting_approval";

  return (
    <div className="mt-2 space-y-2">
      <div className="flex flex-wrap gap-2">
        {isGate && (
          <>
            <button className="rounded bg-green-600 px-2 py-0.5 text-xs text-white" onClick={() => approve.mutate()}>Approve</button>
            <button className="rounded bg-red-600 px-2 py-0.5 text-xs text-white" onClick={() => reject.mutate()}>Reject</button>
          </>
        )}
        {!isTerminal && (
          <button className="rounded border px-2 py-0.5 text-xs" onClick={() => cancel.mutate()}>Cancel</button>
        )}
        <button className="rounded border px-2 py-0.5 text-xs" onClick={() => setEditing((v) => !v)}>Edit</button>
      </div>
      {editing && (
        <div className="space-y-1">
          <input className="w-full rounded border p-1 text-xs" placeholder="branch" value={branch} onChange={(e) => setBranch(e.target.value)} />
          <input className="w-full rounded border p-1 text-xs" placeholder="stage" value={stage} onChange={(e) => setStage(e.target.value)} />
          <button
            className="rounded bg-blue-600 px-2 py-0.5 text-xs text-white"
            onClick={() => { edit.mutate({ branch: branch || undefined, stage: stage || undefined }); setEditing(false); }}
          >
            Save fields
          </button>
        </div>
      )}
      {(cancel.isError || approve.isError || reject.isError || edit.isError) && (
        <p className="text-xs text-red-600">Action failed.</p>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- src/features/runs/RunActions.test.tsx && npm run lint`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add ui/src/features/runs/RunActions.tsx ui/src/features/runs/useRunActions.ts ui/src/features/runs/RunActions.test.tsx
git commit -m "feat: run actions (cancel/approve/reject/edit)"
```

---

# Part F — Integration, E2E, and wiring

## Task F1: Coverage check + full frontend suite

**Files:** none (verification task)

- [ ] **Step 1: Run the whole frontend suite**

Run: `cd ui && npm test`
Expected: all tests pass.

- [ ] **Step 2: Type-check the whole project**

Run: `cd ui && npm run lint`
Expected: no type errors.

- [ ] **Step 3: Run the full backend suite with coverage**

Run: `uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80`
Expected: pass, coverage ≥ 80%.

- [ ] **Step 4: Commit any fixes**

```bash
git add -A && git commit -m "test: green frontend + backend suites for A2" || echo "nothing to commit"
```

## Task F2: Playwright E2E happy path

**Files:**
- Create: `ui/playwright.config.ts`, `ui/e2e/board.spec.ts`, `ui/e2e/README.md`

- [ ] **Step 1: Write the E2E spec**

`ui/playwright.config.ts`:
```typescript
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://localhost:5173" },
  webServer: {
    command: "npm run dev",
    url: "http://localhost:5173",
    reuseExistingServer: true,
  },
});
```

`ui/e2e/board.spec.ts`:
```typescript
import { test, expect } from "@playwright/test";

// Requires the API running on :8000 with a clean dev-user DB and the Vite
// dev server proxying /api. See e2e/README.md.
test("create project, add task, run it", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /new project/i }).click();
  await page.getByLabel(/name/i).fill("E2E Project");
  await page.getByLabel(/local path/i).fill("/tmp/e2e-repo");
  await page.getByRole("button", { name: /^create$/i }).click();

  await page.getByText("E2E Project").click();

  // create an epic -> feature -> task via the hierarchy, then move task to Ready,
  // open it, and start a run. Exact selectors follow the components built above.
  await page.getByRole("button", { name: /add epic/i }).click();
  await page.getByPlaceholder(/new epic title/i).fill("E2E Epic");
  await page.getByRole("button", { name: /^create$/i }).click();
  await expect(page.getByText("E2E Epic")).toBeVisible();
});
```

`ui/e2e/README.md`:
```markdown
# E2E

Prereqs:
1. Backend running: `make dev` (API on :8000, dev auth bypass → dev-user).
2. Frontend dev server is started automatically by Playwright (`webServer`).

Run: `cd ui && npm run e2e`

The happy path exercises: create project → create epic → (manual board steps) →
start run. It uses the real API against the dev profile; reset the dev DB between runs.
```

- [ ] **Step 2: Install browsers and run (manual/CI)**

Run:
```bash
cd ui && npx playwright install --with-deps chromium && make -C .. dev &  # backend
cd ui && npm run e2e
```
Expected: the spec passes against a running backend. If the backend is not available in the execution environment, mark this step as deferred-to-CI and ensure the spec file type-checks: `cd ui && npx tsc -p tsconfig.json --noEmit`.

- [ ] **Step 3: Commit**

```bash
git add ui/playwright.config.ts ui/e2e
git commit -m "test: playwright e2e happy path"
```

## Task F3: Serve UI build from FastAPI + Makefile targets

**Files:**
- Modify: `src/interactors/api/app.py`, `Makefile`
- Test: `tests/integration/test_static_ui.py`

- [ ] **Step 1: Write the failing test**

`tests/integration/test_static_ui.py`:
```python
from fastapi.testclient import TestClient

from interactors.api.app import create_app


def test_api_routes_still_envelope_when_ui_absent():
    # The static mount must not shadow /health or /api-style routes.
    app = create_app()
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `uv run pytest tests/integration/test_static_ui.py -v`
Expected: PASS already (guards against regression). If it fails, the static mount is shadowing routes — fix in Step 3.

- [ ] **Step 3: Add an optional static mount**

In `src/interactors/api/app.py`, after all routers are included and before `return app`, mount the built UI **only if it exists** so tests and API-only deploys are unaffected:

```python
    import os
    from fastapi.staticfiles import StaticFiles

    ui_dist = os.path.join(os.path.dirname(__file__), "..", "..", "..", "ui", "dist")
    if os.path.isdir(ui_dist):
        app.mount("/", StaticFiles(directory=ui_dist, html=True), name="ui")

    return app
```

Add Makefile targets (append to `Makefile`):
```makefile
ui:
	cd ui && npm run dev

ui-build:
	cd ui && npm run build

ui-test:
	cd ui && npm test
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_static_ui.py -v`
Expected: PASS. Also run the full backend suite: `uv run pytest` — still green (the mount is skipped when `ui/dist` is absent).

- [ ] **Step 5: Commit**

```bash
git add src/interactors/api/app.py Makefile tests/integration/test_static_ui.py
git commit -m "feat: serve built ui from fastapi + makefile ui targets"
```

---

## Self-review notes (resolved)

- **Spec §2 in-scope** items each map to a task: projects (C1–C2), board+DnD (D1–D3), ticket panel + acceptance criteria (D4), epic/feature CRUD + filter (D5), run create/list (E1), run cancel/approve/reject/edit (E2 + backend A2–A4). ✅
- **Spec §5.4 run writes** ↔ backend A2 (cancel), A3 (approve/reject), A4 (PATCH), state machine A1. ✅
- **Spec §6 error handling**: ApiError + envelope unwrap (B3), error boundary (B5), optimistic rollback (D2), inline form errors (C2/D4). ✅
- **Spec §7 testing**: backend units/integration (A1–A4), FE unit (B3, D1, D2), FE integration via MSW (C2, D3, D4, D5, E1, E2), Playwright (F2). ✅
- **Spec §8 backend additions / §9 build**: A1–A4 + F3. ✅
- **Gate reachability (§11)**: approve/reject tested via seeded `awaiting_approval` runs (A3) and rendered conditionally (E2). ✅
- **Single-item route**: `GET /work-items/{id}` did not exist (verified against current `work_items.py`); added as **Task A5**, ordered before D4. ✅
- **Backend test helpers verified**: tests reuse the real `make_client()` / `_ready_task(c) -> (task_id, team_id, pid)` helpers in `tests/integration/test_runs_api.py`; the auth-bypass owner is `dev-user`.

## Suggested execution order

Backend Part A (A1→A5) → Frontend B (B1→B5) → C → D (D4 needs A5) → E (E1 stub→E2; E1/E2 need backend A2–A4) → F. Within parts, tasks are sequential.
```
