# C2 — Governance & Observability UIs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four owner-scoped management screens — Budget, Models, Audit log, Memory proposals — over three new backend list endpoints, completing Phase C's observability + model-config surfaces.

**Architecture:** Three new owner-scoped GET list endpoints (mirroring the existing `project_usage` route + repository `.list` pattern), then four React Query screens under `/manage/*` reusing the C1a `ManageLayout`/`ResourceTable`/`ConfirmDialog` shell. No schema/migration changes. The memory diff renderer is extracted into a shared `MemoryDiff` component used by both the inline run card and the new history screen.

**Tech Stack:** Backend — FastAPI + Pydantic v2 + SQLAlchemy 2.0, pytest + TestClient (SQLite in-memory). Frontend — React 18 + TypeScript + Vite + Tailwind, `@tanstack/react-query`, `react-router-dom`, Vitest + Testing Library + MSW. Spec: `docs/specs/2026-06-14-c2-governance-observability-ui-design.md`.

---

## Delivery: 4 PRs

- **PR1** (Tasks 1–3): backend list endpoints `GET /usage`, `GET /audit`, `GET /memory-proposals` + the design/plan docs.
- **PR2** (Tasks 4–7): Budget + Audit screens (data modules, hooks, pages, routing, nav).
- **PR3** (Tasks 8–9): Models (agents) screen.
- **PR4** (Tasks 10–12): Memory proposals screen + shared `MemoryDiff` extraction.

Each PR is built in its own worktree off latest `main`, with `make coverage` + `make lint` (backend) and `npm test` + `npm run lint` + `npm run build` (frontend) green before opening. **PR2–PR4 each rebase on the prior merged PR** (frontend depends on PR1's endpoints).

## Conventions (read once)

- **Backend routes** return the `ok(data, meta=…)` envelope (`interactors/api/envelope`). Repos expose `.list(filters=…, order_by=…, page_size=…, page_number=…)` returning a `PaginatedResult` with `.results/.total/.page_size/.page_number`. Owner scope is auto-applied by the UnitOfWork — **never** filter on `owner_id` yourself.
- **Filter operators** supported by `.list`: equality (`{"run_id": x}`), `__in`, `__gte`, `__lte` (see `usage.py`).
- **Backend tests**: `TestClient(create_app(Settings(_env_file=None, database_url="sqlite:///:memory:", auth_mode="dev")))`; seed via `SqlUnitOfWork(app.state.session_factory, required_filters={"owner_id": "dev-user"})`. Pattern in `tests/integration/test_usage_api.py`.
- **Frontend API base is `/api`** — every fetch path and MSW handler uses `/api/...`. Client helpers in `ui/src/lib/api/client.ts`: `apiGet`, `apiGetPage` (returns `{data, meta}`), `apiPost`, `apiPatch`, `apiPut`, `apiDelete` (envelope-aware; throw `ApiError`).
- **Frontend data modules** export a `*Keys` factory + typed fns (see `lib/api/capabilities.ts`). Hooks: `useQuery` for lists, `useMutation` + `onSuccess: invalidate` for writes (see `useSecrets.ts`).
- **Frontend tests**: inline `QueryClientProvider` (`retry:false`) + `MemoryRouter`; per-test `server.use(http.…("/api/…"))`; `onUnhandledRequest: "error"` — any endpoint a rendered component calls **must** be mocked. MSW server in `ui/src/test/server.ts`, defaults in `ui/src/test/handlers.ts`.
- **Commands** (from `ui/`): `npm test`, `npm run lint` (`tsc --noEmit`), `npm run build`. Single file: `npx vitest run src/features/manage/BudgetPage.test.tsx`. Backend (repo root): `uv run pytest tests/integration/test_audit_api.py -v`, `make coverage`, `make lint`.

---

# PR1 — Backend list endpoints

## Task 1: `GET /usage` — owner-scoped global rollup

**Files:**
- Modify: `src/interactors/api/routes/usage.py`
- Test: `tests/integration/test_usage_global_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_usage_global_api.py
from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def _client():
    return TestClient(
        create_app(Settings(_env_file=None, database_url="sqlite:///:memory:", auth_mode="dev"))
    )


def _seed(client):
    app = client.app
    from adapters.database.uow import SqlUnitOfWork
    from domain.models import Project, Run, RunStage, UsageRecord, WorkItem, WorkItemKind
    uow = SqlUnitOfWork(app.state.session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        for pid in ("p1", "p2"):
            uow.projects.create(Project(id=pid, owner_id="dev-user", name=pid, local_path="/x"))
            uow.work_items.create(WorkItem(id=f"t-{pid}", owner_id="dev-user", project_id=pid,
                                           kind=WorkItemKind.TASK, title="T"))
            uow.runs.create(Run(id=f"r-{pid}", owner_id="dev-user", task_id=f"t-{pid}", team_id="tm"))
        uow.usage.create(UsageRecord(owner_id="dev-user", run_id="r-p1", work_item_id="t-p1",
                                     project_id="p1", stage=RunStage.PLAN, model_id="m1",
                                     input_tokens=10, output_tokens=2, cost_usd=0.1))
        uow.usage.create(UsageRecord(owner_id="dev-user", run_id="r-p2", work_item_id="t-p2",
                                     project_id="p2", stage=RunStage.IMPLEMENT, model_id="m2",
                                     input_tokens=90, output_tokens=8, cost_usd=0.4))


def test_global_usage_rolls_up_all_projects():
    client = _client()
    _seed(client)
    body = client.get("/usage").json()
    assert body["success"] is True
    assert body["data"]["totals"]["input_tokens"] == 100
    assert round(body["data"]["totals"]["cost_usd"], 2) == 0.5


def test_global_usage_filters_by_project():
    client = _client()
    _seed(client)
    data = client.get("/usage", params={"project_id": "p1"}).json()["data"]
    assert data["totals"]["input_tokens"] == 10


def test_global_usage_groups_by_model():
    client = _client()
    _seed(client)
    data = client.get("/usage", params={"group_by": "model"}).json()["data"]
    assert data["group_by"] == "model"
    assert data["groups"]["m1"]["input_tokens"] == 10
    assert data["groups"]["m2"]["input_tokens"] == 90


def test_global_usage_rejects_bad_group():
    client = _client()
    assert client.get("/usage", params={"group_by": "nope"}).status_code == 422


def test_global_usage_rejects_inverted_range():
    client = _client()
    resp = client.get("/usage", params={"since": "2026-02-01T00:00:00Z",
                                        "until": "2026-01-01T00:00:00Z"})
    assert resp.status_code == 422


def test_global_usage_empty_is_zero():
    client = _client()
    data = client.get("/usage").json()["data"]
    assert data["totals"]["total_tokens"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_usage_global_api.py -v`
Expected: FAIL — 404 (route not registered).

- [ ] **Step 3: Add the endpoint**

Append to `src/interactors/api/routes/usage.py` (after `project_usage`). Reuses the module's existing `_validate_group` and `_payload` helpers:

```python
@router.get("/usage")
def global_usage(
    project_id: str | None = Query(default=None),
    group_by: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    uow: UnitOfWork = Depends(get_uow),
) -> dict:
    _validate_group(group_by)
    if since and until and since > until:
        raise HTTPException(status_code=422, detail="since must be <= until")
    filters: dict = {}
    if project_id:
        filters["project_id"] = project_id
    if since:
        filters["created_at__gte"] = since
    if until:
        filters["created_at__lte"] = until
    with uow.transaction():
        records = uow.usage.list(filters=filters, page_size=10000).results
    return ok(_payload(records, group_by))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_usage_global_api.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/interactors/api/routes/usage.py tests/integration/test_usage_global_api.py
git commit -m "feat: owner-scoped global GET /usage rollup endpoint"
```

---

## Task 2: `GET /audit` — owner-scoped audit log list

**Files:**
- Create: `src/interactors/api/routes/audit.py`
- Modify: `src/interactors/api/app.py` (register router)
- Test: `tests/integration/test_audit_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_audit_api.py
from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def _client():
    return TestClient(
        create_app(Settings(_env_file=None, database_url="sqlite:///:memory:", auth_mode="dev"))
    )


def _seed(client):
    app = client.app
    from adapters.database.uow import SqlUnitOfWork
    from domain.models import AuditAction, AuditEvent
    uow = SqlUnitOfWork(app.state.session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        uow.audit_events.create(AuditEvent(owner_id="dev-user", run_id="r1", actor="lead",
                                           action=AuditAction.TOOL_ALLOWED, detail={"tool": "Read"}))
        uow.audit_events.create(AuditEvent(owner_id="dev-user", run_id="r1", actor="lead",
                                           action=AuditAction.TOOL_DENIED, detail={"tool": "Bash"}))
        uow.audit_events.create(AuditEvent(owner_id="dev-user", run_id="r2", actor="eng",
                                           action=AuditAction.CAPABILITY_GRANTED, detail={}))


def test_audit_lists_all_owner_events_newest_first():
    client = _client()
    _seed(client)
    body = client.get("/audit").json()
    assert body["success"] is True
    assert body["meta"]["total"] == 3
    assert len(body["data"]) == 3


def test_audit_filters_by_run():
    client = _client()
    _seed(client)
    data = client.get("/audit", params={"run_id": "r2"}).json()["data"]
    assert len(data) == 1
    assert data[0]["action"] == "capability_granted"


def test_audit_filters_by_action():
    client = _client()
    _seed(client)
    data = client.get("/audit", params={"action": "tool_denied"}).json()["data"]
    assert len(data) == 1
    assert data[0]["detail"]["tool"] == "Bash"


def test_audit_rejects_bad_action():
    client = _client()
    assert client.get("/audit", params={"action": "nope"}).status_code == 422


def test_audit_paginates():
    client = _client()
    _seed(client)
    body = client.get("/audit", params={"page_size": 2, "page_number": 1}).json()
    assert len(body["data"]) == 2
    assert body["meta"]["total"] == 3


def test_audit_empty():
    client = _client()
    body = client.get("/audit").json()
    assert body["data"] == []
    assert body["meta"]["total"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_audit_api.py -v`
Expected: FAIL — 404 (route not registered).

- [ ] **Step 3: Create the router**

```python
# src/interactors/api/routes/audit.py
from fastapi import APIRouter, Depends, HTTPException, Query

from adapters.database.ports import UnitOfWork
from domain.models import AuditAction
from interactors.api.deps import get_uow
from interactors.api.envelope import ok

router = APIRouter(tags=["audit"])

_ACTIONS = {a.value for a in AuditAction}


@router.get("/audit")
def list_audit(
    run_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    page_size: int = Query(50, ge=1, le=200),
    page_number: int = Query(1, ge=1),
    uow: UnitOfWork = Depends(get_uow),
) -> dict:
    if action is not None and action not in _ACTIONS:
        raise HTTPException(status_code=422, detail=f"action must be one of {_ACTIONS}")
    filters: dict = {}
    if run_id:
        filters["run_id"] = run_id
    if action:
        filters["action"] = action
    with uow.transaction():
        page = uow.audit_events.list(
            filters=filters, order_by="-created_at",
            page_size=page_size, page_number=page_number,
        )
    return ok(
        [e.model_dump(mode="json") for e in page.results],
        meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number},
    )
```

- [ ] **Step 4: Register the router**

In `src/interactors/api/app.py`, add `audit` to the `from interactors.api.routes import (...)` block (line ~63) and add after `app.include_router(usage.router)` (line ~84):

```python
    app.include_router(audit.router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_audit_api.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add src/interactors/api/routes/audit.py src/interactors/api/app.py tests/integration/test_audit_api.py
git commit -m "feat: owner-scoped GET /audit log list endpoint"
```

---

## Task 3: `GET /memory-proposals` — owner-scoped proposal history

**Files:**
- Create: `src/interactors/api/routes/memory.py`
- Modify: `src/interactors/api/app.py` (register router)
- Test: `tests/integration/test_memory_list_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_memory_list_api.py
from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def _client():
    return TestClient(
        create_app(Settings(_env_file=None, database_url="sqlite:///:memory:", auth_mode="dev"))
    )


def _seed(client):
    app = client.app
    from adapters.database.uow import SqlUnitOfWork
    from domain.models import MemoryProposal, MemoryProposalStatus
    uow = SqlUnitOfWork(app.state.session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        uow.memory_proposals.create(MemoryProposal(owner_id="dev-user", run_id="r1", project_id="p1",
                                                    branch="b1", diff="--- a\n+++ b\n", files=["CLAUDE.md"],
                                                    status=MemoryProposalStatus.PROPOSED))
        uow.memory_proposals.create(MemoryProposal(owner_id="dev-user", run_id="r2", project_id="p1",
                                                    branch="b2", diff="--- a\n+++ b\n", files=["AGENTS.md"],
                                                    status=MemoryProposalStatus.APPLIED))
        uow.memory_proposals.create(MemoryProposal(owner_id="dev-user", run_id="r3", project_id="p2",
                                                    branch="b3", diff="--- a\n+++ b\n", files=["docs/adr"],
                                                    status=MemoryProposalStatus.REJECTED))


def test_memory_lists_all_owner_proposals():
    client = _client()
    _seed(client)
    body = client.get("/memory-proposals").json()
    assert body["success"] is True
    assert body["meta"]["total"] == 3


def test_memory_filters_by_project():
    client = _client()
    _seed(client)
    data = client.get("/memory-proposals", params={"project_id": "p2"}).json()["data"]
    assert len(data) == 1
    assert data[0]["status"] == "rejected"


def test_memory_filters_by_status():
    client = _client()
    _seed(client)
    data = client.get("/memory-proposals", params={"status": "applied"}).json()["data"]
    assert len(data) == 1
    assert data[0]["files"] == ["AGENTS.md"]


def test_memory_rejects_bad_status():
    client = _client()
    assert client.get("/memory-proposals", params={"status": "nope"}).status_code == 422


def test_memory_paginates():
    client = _client()
    _seed(client)
    body = client.get("/memory-proposals", params={"page_size": 2}).json()
    assert len(body["data"]) == 2
    assert body["meta"]["total"] == 3


def test_memory_empty():
    client = _client()
    body = client.get("/memory-proposals").json()
    assert body["data"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_memory_list_api.py -v`
Expected: FAIL — 404.

- [ ] **Step 3: Create the router**

```python
# src/interactors/api/routes/memory.py
from fastapi import APIRouter, Depends, HTTPException, Query

from adapters.database.ports import UnitOfWork
from domain.models import MemoryProposalStatus
from interactors.api.deps import get_uow
from interactors.api.envelope import ok

router = APIRouter(tags=["memory"])

_STATUSES = {s.value for s in MemoryProposalStatus}


@router.get("/memory-proposals")
def list_memory_proposals(
    project_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page_size: int = Query(50, ge=1, le=200),
    page_number: int = Query(1, ge=1),
    uow: UnitOfWork = Depends(get_uow),
) -> dict:
    if status is not None and status not in _STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {_STATUSES}")
    filters: dict = {}
    if project_id:
        filters["project_id"] = project_id
    if status:
        filters["status"] = status
    with uow.transaction():
        page = uow.memory_proposals.list(
            filters=filters, order_by="-created_at",
            page_size=page_size, page_number=page_number,
        )
    return ok(
        [p.model_dump(mode="json") for p in page.results],
        meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number},
    )
```

- [ ] **Step 4: Register the router**

In `src/interactors/api/app.py`, add `memory` to the routes import block and add after the audit router line:

```python
    app.include_router(memory.router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_memory_list_api.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Verify full backend gate, then commit**

Run: `make coverage && make lint`
Expected: PASS, coverage ≥ 80%.

```bash
git add src/interactors/api/routes/memory.py src/interactors/api/app.py tests/integration/test_memory_list_api.py docs/specs/2026-06-14-c2-governance-observability-ui-design.md docs/plans/2026-06-14-yaah-c2-governance-observability-ui.md
git commit -m "feat: owner-scoped GET /memory-proposals list endpoint"
```

> **PR1 ready.** Push branch, open PR titled `feat: C2 governance/observability list endpoints`. Merge before starting PR2.

---

# PR2 — Budget + Audit screens

> Branch off latest `main` (with PR1 merged).

## Task 4: Data layer — `usage.ts` + `audit.ts`

**Files:**
- Create: `ui/src/lib/api/usage.ts`
- Create: `ui/src/lib/api/audit.ts`
- Test: `ui/src/lib/api/usage.test.ts`
- Test: `ui/src/lib/api/audit.test.ts`

- [ ] **Step 1: Write the failing tests**

```ts
// ui/src/lib/api/usage.test.ts
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { getUsage } from "./usage";

test("getUsage passes group_by and project_id as query params and unwraps totals", async () => {
  let url = "";
  server.use(
    http.get("/api/usage", ({ request }) => {
      url = request.url;
      return HttpResponse.json({
        success: true,
        data: { totals: { input_tokens: 10, output_tokens: 2, cache_read_tokens: 0,
          cache_creation_tokens: 0, cost_usd: 0.1, total_tokens: 12 },
          group_by: "model", groups: { m1: { input_tokens: 10, output_tokens: 2,
            cache_read_tokens: 0, cache_creation_tokens: 0, cost_usd: 0.1, total_tokens: 12 } } },
        error: null,
      });
    }),
  );
  const rollup = await getUsage({ group_by: "model", project_id: "p1" });
  expect(url).toContain("group_by=model");
  expect(url).toContain("project_id=p1");
  expect(rollup.totals.total_tokens).toBe(12);
  expect(rollup.groups?.m1.input_tokens).toBe(10);
});
```

```ts
// ui/src/lib/api/audit.test.ts
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { listAudit } from "./audit";

test("listAudit returns events and meta and forwards filters", async () => {
  let url = "";
  server.use(
    http.get("/api/audit", ({ request }) => {
      url = request.url;
      return HttpResponse.json({
        success: true,
        data: [{ id: "a1", run_id: "r1", stage: null, actor: "lead", action: "tool_denied",
          detail: { tool: "Bash" }, created_at: "2026-06-14T00:00:00Z" }],
        error: null,
        meta: { total: 1, page_size: 50, page_number: 1 },
      });
    }),
  );
  const res = await listAudit({ action: "tool_denied", page_number: 1 });
  expect(url).toContain("action=tool_denied");
  expect(res.data[0].action).toBe("tool_denied");
  expect(res.meta?.total).toBe(1);
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd ui && npx vitest run src/lib/api/usage.test.ts src/lib/api/audit.test.ts`
Expected: FAIL — modules not found.

- [ ] **Step 3: Implement `usage.ts`**

```ts
// ui/src/lib/api/usage.ts
import { apiGet } from "./client";

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_creation_tokens: number;
  cost_usd: number;
  total_tokens: number;
}

export type UsageGroupBy = "stage" | "agent_role" | "model";

export interface UsageRollup {
  totals: TokenUsage;
  group_by?: UsageGroupBy;
  groups?: Record<string, TokenUsage>;
}

export interface UsageParams {
  group_by?: UsageGroupBy;
  project_id?: string;
  since?: string;
  until?: string;
}

export const usageKeys = {
  rollup: (params: UsageParams) => ["usage", params] as const,
};

export async function getUsage(params: UsageParams = {}): Promise<UsageRollup> {
  const qs = new URLSearchParams();
  if (params.group_by) qs.set("group_by", params.group_by);
  if (params.project_id) qs.set("project_id", params.project_id);
  if (params.since) qs.set("since", params.since);
  if (params.until) qs.set("until", params.until);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return apiGet<UsageRollup>(`/usage${suffix}`);
}
```

- [ ] **Step 4: Implement `audit.ts`**

```ts
// ui/src/lib/api/audit.ts
import { apiGetPage } from "./client";
import type { PageMeta } from "./client";

export type AuditAction = "capability_granted" | "tool_allowed" | "tool_denied";

export interface AuditEvent {
  id: string;
  run_id: string;
  stage: string | null;
  actor: string;
  action: AuditAction;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface AuditParams {
  run_id?: string;
  action?: AuditAction;
  page_number?: number;
  page_size?: number;
}

export const auditKeys = {
  list: (params: AuditParams) => ["audit", params] as const,
};

export async function listAudit(
  params: AuditParams = {},
): Promise<{ data: AuditEvent[]; meta?: PageMeta }> {
  const qs = new URLSearchParams();
  if (params.run_id) qs.set("run_id", params.run_id);
  if (params.action) qs.set("action", params.action);
  qs.set("page_number", String(params.page_number ?? 1));
  qs.set("page_size", String(params.page_size ?? 50));
  return apiGetPage<AuditEvent[]>(`/audit?${qs.toString()}`);
}
```

- [ ] **Step 5: Run to verify they pass**

Run: `cd ui && npx vitest run src/lib/api/usage.test.ts src/lib/api/audit.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ui/src/lib/api/usage.ts ui/src/lib/api/audit.ts ui/src/lib/api/usage.test.ts ui/src/lib/api/audit.test.ts
git commit -m "feat(ui): usage + audit api data modules"
```

---

## Task 5: Budget screen (`/manage/usage`)

**Files:**
- Create: `ui/src/features/manage/useUsage.ts`
- Create: `ui/src/features/manage/BudgetPage.tsx`
- Test: `ui/src/features/manage/BudgetPage.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// ui/src/features/manage/BudgetPage.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { BudgetPage } from "./BudgetPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><BudgetPage /></MemoryRouter>
    </QueryClientProvider>,
  );
}

const TOTALS = { input_tokens: 100, output_tokens: 10, cache_read_tokens: 0,
  cache_creation_tokens: 0, cost_usd: 0.5, total_tokens: 110 };

test("renders totals and switches group-by", async () => {
  server.use(
    http.get("/api/usage", ({ request }) => {
      const group = new URL(request.url).searchParams.get("group_by");
      return HttpResponse.json({
        success: true,
        data: group
          ? { totals: TOTALS, group_by: group, groups: { m1: TOTALS } }
          : { totals: TOTALS },
        error: null,
      });
    }),
  );
  renderPage();
  expect(await screen.findByText(/\$0\.50/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /model/i }));
  expect(await screen.findByText("m1")).toBeInTheDocument();
});

test("shows error state", async () => {
  server.use(
    http.get("/api/usage", () =>
      HttpResponse.json({ success: false, data: null, error: "boom" }, { status: 500 }),
    ),
  );
  renderPage();
  expect(await screen.findByText(/boom/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ui && npx vitest run src/features/manage/BudgetPage.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the hook**

```ts
// ui/src/features/manage/useUsage.ts
import { useQuery } from "@tanstack/react-query";
import { getUsage, usageKeys, type UsageParams } from "../../lib/api/usage";

export function useUsage(params: UsageParams) {
  return useQuery({ queryKey: usageKeys.rollup(params), queryFn: () => getUsage(params) });
}
```

- [ ] **Step 4: Implement the page**

```tsx
// ui/src/features/manage/BudgetPage.tsx
import { useState } from "react";
import type { TokenUsage, UsageGroupBy } from "../../lib/api/usage";
import { useUsage } from "./useUsage";

const GROUPS: { value: UsageGroupBy; label: string }[] = [
  { value: "stage", label: "Stage" },
  { value: "agent_role", label: "Role" },
  { value: "model", label: "Model" },
];

function fmtCost(n: number) { return `$${n.toFixed(2)}`; }

function Totals({ t }: { t: TokenUsage }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {[
        ["Cost", fmtCost(t.cost_usd)],
        ["Total tokens", t.total_tokens.toLocaleString()],
        ["Input", t.input_tokens.toLocaleString()],
        ["Output", t.output_tokens.toLocaleString()],
      ].map(([label, value]) => (
        <div key={label} className="rounded border p-3">
          <div className="text-xs text-gray-500">{label}</div>
          <div className="text-lg font-semibold">{value}</div>
        </div>
      ))}
    </div>
  );
}

export function BudgetPage() {
  const [group, setGroup] = useState<UsageGroupBy | null>(null);
  const { data, isLoading, isError, error } = useUsage(group ? { group_by: group } : {});

  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">Budget</h1>
      <div className="mb-4 flex gap-2">
        <button
          onClick={() => setGroup(null)}
          className={`rounded px-3 py-1 text-sm ${group === null ? "bg-blue-600 text-white" : "border"}`}
        >Total</button>
        {GROUPS.map((g) => (
          <button
            key={g.value}
            onClick={() => setGroup(g.value)}
            className={`rounded px-3 py-1 text-sm ${group === g.value ? "bg-blue-600 text-white" : "border"}`}
          >{g.label}</button>
        ))}
      </div>
      {isLoading && <p className="text-sm text-gray-500">Loading…</p>}
      {isError && <p className="text-sm text-red-600">{(error as Error).message}</p>}
      {data && (
        <>
          <Totals t={data.totals} />
          {data.groups && (
            <table className="mt-6 w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="py-2">{GROUPS.find((g) => g.value === data.group_by)?.label}</th>
                  <th>Cost</th><th>Tokens</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.groups).map(([key, u]) => (
                  <tr key={key} className="border-b">
                    <td className="py-2 font-medium">{key}</td>
                    <td>{fmtCost(u.cost_usd)}</td>
                    <td>{u.total_tokens.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd ui && npx vitest run src/features/manage/BudgetPage.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ui/src/features/manage/useUsage.ts ui/src/features/manage/BudgetPage.tsx ui/src/features/manage/BudgetPage.test.tsx
git commit -m "feat(ui): Budget screen with group-by toggle"
```

---

## Task 6: Audit screen (`/manage/audit`)

**Files:**
- Create: `ui/src/features/manage/useAudit.ts`
- Create: `ui/src/features/manage/AuditPage.tsx`
- Test: `ui/src/features/manage/AuditPage.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// ui/src/features/manage/AuditPage.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { AuditPage } from "./AuditPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><AuditPage /></MemoryRouter>
    </QueryClientProvider>,
  );
}

test("renders events and filters by action", async () => {
  server.use(
    http.get("/api/audit", ({ request }) => {
      const action = new URL(request.url).searchParams.get("action");
      const all = [
        { id: "a1", run_id: "r1", stage: null, actor: "lead", action: "tool_allowed",
          detail: { tool: "Read" }, created_at: "2026-06-14T00:00:00Z" },
        { id: "a2", run_id: "r1", stage: null, actor: "lead", action: "tool_denied",
          detail: { tool: "Bash" }, created_at: "2026-06-14T00:01:00Z" },
      ];
      const data = action ? all.filter((e) => e.action === action) : all;
      return HttpResponse.json({ success: true, data, error: null,
        meta: { total: data.length, page_size: 50, page_number: 1 } });
    }),
  );
  renderPage();
  expect(await screen.findByText("Read")).toBeInTheDocument();
  await userEvent.selectOptions(screen.getByLabelText(/action/i), "tool_denied");
  expect(await screen.findByText("Bash")).toBeInTheDocument();
  expect(screen.queryByText("Read")).not.toBeInTheDocument();
});

test("shows empty state", async () => {
  server.use(
    http.get("/api/audit", () =>
      HttpResponse.json({ success: true, data: [], error: null,
        meta: { total: 0, page_size: 50, page_number: 1 } }),
    ),
  );
  renderPage();
  expect(await screen.findByText(/no audit events/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ui && npx vitest run src/features/manage/AuditPage.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement the hook**

```ts
// ui/src/features/manage/useAudit.ts
import { useQuery } from "@tanstack/react-query";
import { auditKeys, listAudit, type AuditParams } from "../../lib/api/audit";

export function useAudit(params: AuditParams) {
  return useQuery({ queryKey: auditKeys.list(params), queryFn: () => listAudit(params) });
}
```

- [ ] **Step 4: Implement the page**

```tsx
// ui/src/features/manage/AuditPage.tsx
import { useState } from "react";
import type { AuditAction } from "../../lib/api/audit";
import { useAudit } from "./useAudit";

const ACTIONS: AuditAction[] = ["capability_granted", "tool_allowed", "tool_denied"];

const badgeClass: Record<AuditAction, string> = {
  capability_granted: "bg-blue-100 text-blue-800",
  tool_allowed: "bg-green-100 text-green-800",
  tool_denied: "bg-red-100 text-red-800",
};

export function AuditPage() {
  const [action, setAction] = useState<AuditAction | "">("");
  const [page, setPage] = useState(1);
  const params = { page_number: page, ...(action ? { action } : {}) };
  const { data, isLoading, isError, error } = useAudit(params);
  const rows = data?.data ?? [];
  const total = data?.meta?.total ?? 0;
  const pageSize = data?.meta?.page_size ?? 50;

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Audit log</h1>
        <label className="text-sm">
          Action{" "}
          <select
            className="rounded border p-1"
            value={action}
            onChange={(e) => { setAction(e.target.value as AuditAction | ""); setPage(1); }}
          >
            <option value="">All</option>
            {ACTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        </label>
      </div>
      {isLoading && <p className="text-sm text-gray-500">Loading…</p>}
      {isError && <p className="text-sm text-red-600">{(error as Error).message}</p>}
      {!isLoading && rows.length === 0 && <p className="text-sm text-gray-500">No audit events.</p>}
      {rows.length > 0 && (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-gray-500">
              <th className="py-2">Time</th><th>Actor</th><th>Action</th><th>Run</th><th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((e) => (
              <tr key={e.id} className="border-b align-top">
                <td className="py-2 text-gray-600">{new Date(e.created_at).toLocaleString()}</td>
                <td>{e.actor}</td>
                <td><span className={`rounded px-1.5 py-0.5 text-xs ${badgeClass[e.action]}`}>{e.action}</span></td>
                <td className="font-mono text-xs">{e.run_id}</td>
                <td className="text-gray-600">{JSON.stringify(e.detail)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="mt-4 flex items-center gap-3 text-sm">
        <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}
          className="rounded border px-2 py-1 disabled:opacity-50">Prev</button>
        <span>Page {page}</span>
        <button disabled={page * pageSize >= total} onClick={() => setPage((p) => p + 1)}
          className="rounded border px-2 py-1 disabled:opacity-50">Next</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd ui && npx vitest run src/features/manage/AuditPage.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ui/src/features/manage/useAudit.ts ui/src/features/manage/AuditPage.tsx ui/src/features/manage/AuditPage.test.tsx
git commit -m "feat(ui): Audit log screen with action filter + pagination"
```

---

## Task 7: Wire Budget + Audit into routing & nav

**Files:**
- Modify: `ui/src/features/manage/ManageLayout.tsx`
- Modify: `ui/src/app/router.tsx`
- Test: `ui/src/features/manage/ManageLayout.test.tsx` (create)

- [ ] **Step 1: Write the failing test**

```tsx
// ui/src/features/manage/ManageLayout.test.tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ManageLayout } from "./ManageLayout";

test("sidebar lists all manage sections", () => {
  render(<MemoryRouter><ManageLayout /></MemoryRouter>);
  for (const label of ["Secrets", "Skills", "MCP servers", "Budget", "Models", "Audit", "Memory"]) {
    expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
  }
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ui && npx vitest run src/features/manage/ManageLayout.test.tsx`
Expected: FAIL — Budget/Models/Audit/Memory links absent.

- [ ] **Step 3: Add nav items**

In `ui/src/features/manage/ManageLayout.tsx`, extend the `items` array:

```ts
const items = [
  { to: "/manage/secrets", label: "Secrets" },
  { to: "/manage/skills", label: "Skills" },
  { to: "/manage/mcp-servers", label: "MCP servers" },
  { to: "/manage/usage", label: "Budget" },
  { to: "/manage/models", label: "Models" },
  { to: "/manage/audit", label: "Audit" },
  { to: "/manage/memory", label: "Memory" },
];
```

- [ ] **Step 4: Add routes (Budget + Audit now; Models/Memory added in their PRs)**

In `ui/src/app/router.tsx`, add imports and child routes under `/manage`:

```tsx
import { BudgetPage } from "../features/manage/BudgetPage";
import { AuditPage } from "../features/manage/AuditPage";
```

```tsx
          { path: "usage", element: <BudgetPage /> },
          { path: "audit", element: <AuditPage /> },
```

> **Note:** the `Models` and `Memory` nav links will 404 until PR3/PR4 add their routes. This is the chosen approach — all nav labels appear now; routes land per-PR. (Acceptable mid-stack since PRs merge in order.)

- [ ] **Step 5: Run lint + build + full UI suite**

Run: `cd ui && npm run lint && npm test && npm run build`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ui/src/features/manage/ManageLayout.tsx ui/src/app/router.tsx ui/src/features/manage/ManageLayout.test.tsx
git commit -m "feat(ui): route + nav for Budget and Audit screens"
```

> **PR2 ready.** Push, open PR `feat: C2 Budget + Audit screens`. Merge before PR3.

---

# PR3 — Models (agents) screen

> Branch off latest `main` (PR2 merged).

## Task 8: Data layer — `teams.ts` + `agents.ts`

**Files:**
- Create: `ui/src/lib/api/teams.ts`
- Create: `ui/src/lib/api/agents.ts`
- Test: `ui/src/lib/api/agents.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// ui/src/lib/api/agents.test.ts
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { listAgents, updateAgent } from "./agents";
import { listTeams } from "./teams";

const AGENT = { id: "ag1", team_id: "tm1", role: "engineer", name: "Eng", persona: "",
  model_alias: "sonnet", runtime: "claude_code", purpose: "", system_prompt: "",
  allowed_tools: ["Read"], skill_ids: [], mcp_server_ids: [], secret_ids: [] };

test("listTeams unwraps the envelope", async () => {
  server.use(
    http.get("/api/teams", () =>
      HttpResponse.json({ success: true, data: [{ id: "tm1", owner_id: "u", name: "Default",
        created_at: "2026-06-14T00:00:00Z" }], error: null,
        meta: { total: 1, page_size: 100, page_number: 1 } }),
    ),
  );
  const teams = await listTeams();
  expect(teams[0].name).toBe("Default");
});

test("listAgents returns agents for a team", async () => {
  server.use(
    http.get("/api/teams/tm1/agents", () =>
      HttpResponse.json({ success: true, data: [AGENT], error: null,
        meta: { total: 1, page_size: 100, page_number: 1 } }),
    ),
  );
  const agents = await listAgents("tm1");
  expect(agents[0].model_alias).toBe("sonnet");
});

test("updateAgent PATCHes model_alias", async () => {
  let body: unknown = null;
  server.use(
    http.patch("/api/agents/ag1", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ success: true, data: { ...AGENT, model_alias: "opus" }, error: null });
    }),
  );
  const updated = await updateAgent("ag1", { model_alias: "opus" });
  expect(body).toEqual({ model_alias: "opus" });
  expect(updated.model_alias).toBe("opus");
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ui && npx vitest run src/lib/api/agents.test.ts`
Expected: FAIL — modules not found.

- [ ] **Step 3: Implement `teams.ts`**

```ts
// ui/src/lib/api/teams.ts
import { apiGetPage } from "./client";

export interface Team {
  id: string;
  owner_id: string;
  name: string;
  created_at: string;
}

export const teamKeys = { all: ["teams"] as const };

export async function listTeams(): Promise<Team[]> {
  return (await apiGetPage<Team[]>("/teams")).data;
}
```

- [ ] **Step 4: Implement `agents.ts`**

```ts
// ui/src/lib/api/agents.ts
import { apiGetPage, apiPatch } from "./client";

export interface Agent {
  id: string;
  team_id: string;
  role: string;
  name: string;
  persona: string;
  model_alias: string;
  runtime: string;
  purpose: string;
  system_prompt: string;
  allowed_tools: string[];
  skill_ids: string[];
  mcp_server_ids: string[];
  secret_ids: string[];
}

export interface UpdateAgentInput {
  name?: string;
  model_alias?: string;
  allowed_tools?: string[];
  skill_ids?: string[];
  mcp_server_ids?: string[];
  secret_ids?: string[];
}

export const agentKeys = {
  forTeam: (teamId: string) => ["agents", teamId] as const,
};

export async function listAgents(teamId: string): Promise<Agent[]> {
  return (await apiGetPage<Agent[]>(`/teams/${teamId}/agents?page_size=200`)).data;
}

export async function updateAgent(id: string, input: UpdateAgentInput): Promise<Agent> {
  return apiPatch<Agent>(`/agents/${id}`, input);
}
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd ui && npx vitest run src/lib/api/agents.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ui/src/lib/api/teams.ts ui/src/lib/api/agents.ts ui/src/lib/api/agents.test.ts
git commit -m "feat(ui): teams + agents api data modules"
```

---

## Task 9: Models screen (`/manage/models`) + routing

**Files:**
- Create: `ui/src/features/manage/useAgents.ts`
- Create: `ui/src/features/manage/ModelsPage.tsx`
- Modify: `ui/src/app/router.tsx`
- Test: `ui/src/features/manage/ModelsPage.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// ui/src/features/manage/ModelsPage.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { ModelsPage } from "./ModelsPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><ModelsPage /></MemoryRouter>
    </QueryClientProvider>,
  );
}

const AGENT = { id: "ag1", team_id: "tm1", role: "engineer", name: "Eng", persona: "",
  model_alias: "sonnet", runtime: "claude_code", purpose: "", system_prompt: "",
  allowed_tools: ["Read"], skill_ids: [], mcp_server_ids: [], secret_ids: [] };

function mockHappyPath() {
  server.use(
    http.get("/api/teams", () =>
      HttpResponse.json({ success: true, data: [{ id: "tm1", owner_id: "u", name: "Default",
        created_at: "2026-06-14T00:00:00Z" }], error: null,
        meta: { total: 1, page_size: 100, page_number: 1 } }),
    ),
    http.get("/api/teams/tm1/agents", () =>
      HttpResponse.json({ success: true, data: [AGENT], error: null,
        meta: { total: 1, page_size: 200, page_number: 1 } }),
    ),
  );
}

test("lists agents for the first team", async () => {
  mockHappyPath();
  renderPage();
  expect(await screen.findByText("Eng")).toBeInTheDocument();
  expect(screen.getByText("sonnet")).toBeInTheDocument();
});

test("edits model_alias via PATCH", async () => {
  mockHappyPath();
  let patched: unknown = null;
  server.use(
    http.patch("/api/agents/ag1", async ({ request }) => {
      patched = await request.json();
      return HttpResponse.json({ success: true, data: { ...AGENT, model_alias: "opus" }, error: null });
    }),
  );
  renderPage();
  await userEvent.click(await screen.findByRole("button", { name: /edit/i }));
  const input = screen.getByLabelText(/model alias/i);
  await userEvent.clear(input);
  await userEvent.type(input, "opus");
  await userEvent.click(screen.getByRole("button", { name: /save/i }));
  await waitFor(() => expect(patched).toEqual({ model_alias: "opus", allowed_tools: ["Read"] }));
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ui && npx vitest run src/features/manage/ModelsPage.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement the hooks**

```ts
// ui/src/features/manage/useAgents.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { teamKeys, listTeams } from "../../lib/api/teams";
import { agentKeys, listAgents, updateAgent, type UpdateAgentInput } from "../../lib/api/agents";

export function useTeams() {
  return useQuery({ queryKey: teamKeys.all, queryFn: listTeams });
}

export function useAgents(teamId: string | undefined) {
  return useQuery({
    queryKey: agentKeys.forTeam(teamId ?? ""),
    queryFn: () => listAgents(teamId as string),
    enabled: Boolean(teamId),
  });
}

export function useUpdateAgent(teamId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (a: { id: string; input: UpdateAgentInput }) => updateAgent(a.id, a.input),
    onSuccess: () => qc.invalidateQueries({ queryKey: agentKeys.forTeam(teamId) }),
  });
}
```

- [ ] **Step 4: Implement the page**

```tsx
// ui/src/features/manage/ModelsPage.tsx
import { useEffect, useState } from "react";
import type { Agent } from "../../lib/api/agents";
import { ResourceTable } from "../components/ResourceTable";
import { useAgents, useTeams, useUpdateAgent } from "./useAgents";

interface Draft { model_alias: string; allowed_tools: string }

export function ModelsPage() {
  const teams = useTeams();
  const [teamId, setTeamId] = useState<string | undefined>(undefined);
  useEffect(() => {
    if (!teamId && teams.data && teams.data.length > 0) setTeamId(teams.data[0].id);
  }, [teams.data, teamId]);

  const agents = useAgents(teamId);
  const update = useUpdateAgent(teamId ?? "");
  const [editing, setEditing] = useState<Agent | null>(null);
  const [draft, setDraft] = useState<Draft>({ model_alias: "", allowed_tools: "" });

  function openEdit(a: Agent) {
    setDraft({ model_alias: a.model_alias, allowed_tools: a.allowed_tools.join(", ") });
    setEditing(a);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!editing) return;
    await update.mutateAsync({
      id: editing.id,
      input: {
        model_alias: draft.model_alias,
        allowed_tools: draft.allowed_tools.split(",").map((t) => t.trim()).filter(Boolean),
      },
    });
    setEditing(null);
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Models</h1>
        {teams.data && teams.data.length > 0 && (
          <label className="text-sm">
            Team{" "}
            <select className="rounded border p-1" value={teamId ?? ""}
              onChange={(e) => setTeamId(e.target.value)}>
              {teams.data.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </label>
        )}
      </div>
      {agents.isLoading && <p className="text-sm text-gray-500">Loading…</p>}
      {agents.isError && <p className="text-sm text-red-600">{(agents.error as Error).message}</p>}
      <ResourceTable
        rows={agents.data ?? []}
        rowKey={(a) => a.id}
        empty="No agents in this team."
        columns={[
          { header: "Role", render: (a) => <span className="text-gray-600">{a.role}</span> },
          { header: "Name", render: (a) => <span className="font-medium">{a.name}</span> },
          { header: "Model", render: (a) => <span className="font-mono text-xs">{a.model_alias}</span> },
          { header: "Runtime", render: (a) => <span className="text-gray-600">{a.runtime}</span> },
        ]}
        actions={(a) => (
          <button onClick={() => openEdit(a)} className="text-sm text-blue-700">Edit</button>
        )}
      />

      {editing && (
        <div className="fixed inset-0 grid place-items-center bg-black/30">
          <form onSubmit={submit} className="w-96 space-y-3 rounded bg-white p-4 shadow">
            <h2 className="text-lg font-semibold">Edit {editing.name}</h2>
            <label className="block text-sm">Model alias
              <input className="mt-1 w-full rounded border p-2" value={draft.model_alias}
                onChange={(e) => setDraft({ ...draft, model_alias: e.target.value })} />
            </label>
            <label className="block text-sm">Allowed tools (comma-separated)
              <input className="mt-1 w-full rounded border p-2" value={draft.allowed_tools}
                onChange={(e) => setDraft({ ...draft, allowed_tools: e.target.value })} />
            </label>
            {update.isError && <p className="text-xs text-red-600">{(update.error as Error).message}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setEditing(null)} className="rounded px-3 py-1 text-sm">Cancel</button>
              <button type="submit" disabled={update.isPending}
                className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50">Save</button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Add the route**

In `ui/src/app/router.tsx`, add the import and child route:

```tsx
import { ModelsPage } from "../features/manage/ModelsPage";
```

```tsx
          { path: "models", element: <ModelsPage /> },
```

- [ ] **Step 6: Run to verify it passes, then full gate**

Run: `cd ui && npx vitest run src/features/manage/ModelsPage.test.tsx`
Expected: PASS.
Run: `cd ui && npm run lint && npm test && npm run build`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add ui/src/features/manage/useAgents.ts ui/src/features/manage/ModelsPage.tsx ui/src/features/manage/ModelsPage.test.tsx ui/src/app/router.tsx
git commit -m "feat(ui): Models screen — per-agent model_alias + tool grants"
```

> **PR3 ready.** Push, open PR `feat: C2 Models screen`. Merge before PR4.

---

# PR4 — Memory proposals screen + shared diff

> Branch off latest `main` (PR3 merged).

## Task 10: Extract shared `MemoryDiff` component

**Files:**
- Create: `ui/src/features/runs/MemoryDiff.tsx`
- Modify: `ui/src/features/runs/MemoryProposalCard.tsx`
- Test: `ui/src/features/runs/MemoryDiff.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// ui/src/features/runs/MemoryDiff.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryDiff } from "./MemoryDiff";

test("hidden by default, toggles diff open", async () => {
  render(<MemoryDiff diff={"--- a\n+++ b\n+added line"} />);
  expect(screen.queryByText(/added line/)).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /show diff/i }));
  expect(screen.getByText(/added line/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /hide diff/i }));
  expect(screen.queryByText(/added line/)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ui && npx vitest run src/features/runs/MemoryDiff.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Create the component**

```tsx
// ui/src/features/runs/MemoryDiff.tsx
import { useState } from "react";

export function MemoryDiff({ diff }: { diff: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button className="text-blue-700 underline" onClick={() => setOpen((v) => !v)}>
        {open ? "Hide diff" : "Show diff"}
      </button>
      {open && (
        <pre className="mt-1 max-h-64 overflow-auto rounded bg-white p-2 text-[11px]">{diff}</pre>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Refactor `MemoryProposalCard` to use it**

In `ui/src/features/runs/MemoryProposalCard.tsx`: remove the local `open` state, the "Show diff/Hide diff" toggle button, and the `<pre>…proposal.diff…</pre>` block; replace them with `<MemoryDiff diff={proposal.diff} />`. Add `import { MemoryDiff } from "./MemoryDiff";` and drop the now-unused `useState` import. The replaced region (between the `<ul>` files list and the `isProposed` block) becomes:

```tsx
      <ul className="mt-1 list-disc pl-4 text-gray-700">
        {proposal.files.map((f) => (
          <li key={f}>{f}</li>
        ))}
      </ul>
      <MemoryDiff diff={proposal.diff} />
```

- [ ] **Step 5: Run to verify both pass**

Run: `cd ui && npx vitest run src/features/runs/`
Expected: PASS (MemoryDiff + existing MemoryProposalCard tests).

- [ ] **Step 6: Commit**

```bash
git add ui/src/features/runs/MemoryDiff.tsx ui/src/features/runs/MemoryProposalCard.tsx ui/src/features/runs/MemoryDiff.test.tsx
git commit -m "refactor(ui): extract shared MemoryDiff component"
```

---

## Task 11: Memory list api

**Files:**
- Modify: `ui/src/lib/api/memory.ts`
- Test: `ui/src/lib/api/memory.test.ts` (create)

- [ ] **Step 1: Write the failing test**

```ts
// ui/src/lib/api/memory.test.ts
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { listMemoryProposals } from "./memory";

test("listMemoryProposals returns proposals + meta and forwards filters", async () => {
  let url = "";
  server.use(
    http.get("/api/memory-proposals", ({ request }) => {
      url = request.url;
      return HttpResponse.json({
        success: true,
        data: [{ id: "m1", run_id: "r1", project_id: "p1", branch: "b", diff: "d",
          files: ["CLAUDE.md"], status: "applied", pr_url: null, resolved_at: null,
          created_at: "2026-06-14T00:00:00Z" }],
        error: null,
        meta: { total: 1, page_size: 50, page_number: 1 },
      });
    }),
  );
  const res = await listMemoryProposals({ status: "applied" });
  expect(url).toContain("status=applied");
  expect(res.data[0].status).toBe("applied");
  expect(res.meta?.total).toBe(1);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ui && npx vitest run src/lib/api/memory.test.ts`
Expected: FAIL — `listMemoryProposals` not exported.

- [ ] **Step 3: Extend `memory.ts`**

In `ui/src/lib/api/memory.ts`: merge the import line to `import { apiGet, apiGetPage, apiPost } from "./client";` and add `import type { PageMeta } from "./client";`. Add `created_at: string;` to the `MemoryProposal` interface. Then append:

```ts
export interface MemoryListParams {
  project_id?: string;
  status?: MemoryProposalStatus;
  page_number?: number;
  page_size?: number;
}

export const memoryListKeys = {
  list: (params: MemoryListParams) => ["memory-proposals", params] as const,
};

export async function listMemoryProposals(
  params: MemoryListParams = {},
): Promise<{ data: MemoryProposal[]; meta?: PageMeta }> {
  const qs = new URLSearchParams();
  if (params.project_id) qs.set("project_id", params.project_id);
  if (params.status) qs.set("status", params.status);
  qs.set("page_number", String(params.page_number ?? 1));
  qs.set("page_size", String(params.page_size ?? 50));
  return apiGetPage<MemoryProposal[]>(`/memory-proposals?${qs.toString()}`);
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd ui && npx vitest run src/lib/api/memory.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/lib/api/memory.ts ui/src/lib/api/memory.test.ts
git commit -m "feat(ui): listMemoryProposals api"
```

---

## Task 12: Memory proposals screen (`/manage/memory`) + routing

**Files:**
- Create: `ui/src/features/manage/useMemoryProposals.ts`
- Create: `ui/src/features/manage/MemoryPage.tsx`
- Modify: `ui/src/app/router.tsx`
- Test: `ui/src/features/manage/MemoryPage.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// ui/src/features/manage/MemoryPage.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { MemoryPage } from "./MemoryPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><MemoryPage /></MemoryRouter>
    </QueryClientProvider>,
  );
}

const PROPOSAL = { id: "m1", run_id: "r1", project_id: "p1", branch: "b", diff: "+new",
  files: ["CLAUDE.md"], status: "applied", pr_url: null, resolved_at: null,
  created_at: "2026-06-14T00:00:00Z" };

test("renders proposals and expands diff", async () => {
  server.use(
    http.get("/api/memory-proposals", () =>
      HttpResponse.json({ success: true, data: [PROPOSAL], error: null,
        meta: { total: 1, page_size: 50, page_number: 1 } }),
    ),
  );
  renderPage();
  expect(await screen.findByText("CLAUDE.md")).toBeInTheDocument();
  expect(screen.getByText("applied")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /show diff/i }));
  expect(screen.getByText("+new")).toBeInTheDocument();
});

test("filters by status", async () => {
  let url = "";
  server.use(
    http.get("/api/memory-proposals", ({ request }) => {
      url = request.url;
      return HttpResponse.json({ success: true, data: [], error: null,
        meta: { total: 0, page_size: 50, page_number: 1 } });
    }),
  );
  renderPage();
  await userEvent.selectOptions(await screen.findByLabelText(/status/i), "rejected");
  expect(url).toContain("status=rejected");
  expect(await screen.findByText(/no memory proposals/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ui && npx vitest run src/features/manage/MemoryPage.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement the hook**

```ts
// ui/src/features/manage/useMemoryProposals.ts
import { useQuery } from "@tanstack/react-query";
import { listMemoryProposals, memoryListKeys, type MemoryListParams } from "../../lib/api/memory";

export function useMemoryProposals(params: MemoryListParams) {
  return useQuery({ queryKey: memoryListKeys.list(params), queryFn: () => listMemoryProposals(params) });
}
```

- [ ] **Step 4: Implement the page**

```tsx
// ui/src/features/manage/MemoryPage.tsx
import { useState } from "react";
import type { MemoryProposalStatus } from "../../lib/api/memory";
import { MemoryDiff } from "../runs/MemoryDiff";
import { useMemoryProposals } from "./useMemoryProposals";

const STATUSES: MemoryProposalStatus[] = ["proposed", "applied", "rejected"];

const badgeClass: Record<MemoryProposalStatus, string> = {
  proposed: "bg-amber-100 text-amber-800",
  applied: "bg-green-100 text-green-800",
  rejected: "bg-gray-200 text-gray-700",
};

export function MemoryPage() {
  const [status, setStatus] = useState<MemoryProposalStatus | "">("");
  const { data, isLoading, isError, error } = useMemoryProposals(status ? { status } : {});
  const rows = data?.data ?? [];

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Memory proposals</h1>
        <label className="text-sm">
          Status{" "}
          <select className="rounded border p-1" value={status}
            onChange={(e) => setStatus(e.target.value as MemoryProposalStatus | "")}>
            <option value="">All</option>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
      </div>
      {isLoading && <p className="text-sm text-gray-500">Loading…</p>}
      {isError && <p className="text-sm text-red-600">{(error as Error).message}</p>}
      {!isLoading && rows.length === 0 && <p className="text-sm text-gray-500">No memory proposals.</p>}
      <ul className="space-y-3">
        {rows.map((p) => (
          <li key={p.id} className="rounded border p-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="font-medium">{p.files.join(", ")}</span>
              <span className={`rounded px-1.5 py-0.5 text-xs ${badgeClass[p.status]}`}>{p.status}</span>
            </div>
            <div className="mt-1 text-xs text-gray-500">
              project {p.project_id} · {new Date(p.created_at).toLocaleString()}
            </div>
            <div className="mt-2"><MemoryDiff diff={p.diff} /></div>
            {p.pr_url && (
              <a className="mt-1 block text-blue-700 underline" href={p.pr_url}>View PR</a>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 5: Add the route**

In `ui/src/app/router.tsx`, add the import and child route:

```tsx
import { MemoryPage } from "../features/manage/MemoryPage";
```

```tsx
          { path: "memory", element: <MemoryPage /> },
```

- [ ] **Step 6: Run to verify it passes, then full gate**

Run: `cd ui && npx vitest run src/features/manage/MemoryPage.test.tsx`
Expected: PASS.
Run: `cd ui && npm run lint && npm test && npm run build`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add ui/src/features/manage/useMemoryProposals.ts ui/src/features/manage/MemoryPage.tsx ui/src/features/manage/MemoryPage.test.tsx ui/src/app/router.tsx
git commit -m "feat(ui): Memory proposals history screen"
```

> **PR4 ready.** Push, open PR `feat: C2 Memory proposals screen`. This completes C2.

---

## Self-review notes (verified against spec)

- **Spec coverage:** `GET /usage` (Task 1), `GET /audit` (Task 2), `GET /memory-proposals` (Task 3); Budget (Task 5), Models (Task 9), Audit (Task 6), Memory (Task 12); shared `MemoryDiff` (Task 10); nav for all four (Task 7 + per-PR routes). Each spec success-criterion clause maps to a task.
- **Owner-scoping/filters/pagination/empty:** covered by backend tests in Tasks 1–3; `since>until`→422 (Task 1), bad `group_by`/`action`/`status`→422 (Tasks 1–3).
- **Type consistency:** `UsageRollup.totals: TokenUsage`, `AuditEvent.action: AuditAction`, `Agent.model_alias: string`, `MemoryProposal.status: MemoryProposalStatus` are used identically across api modules, hooks, and pages. `PageMeta` is imported from `./client` (already exported there).
- **Out-of-scope respected:** no model registry, no agent create/delete, no project-scoped audit, no apply/reject on the memory history screen.
