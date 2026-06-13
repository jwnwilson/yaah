# C1a Capability & Governance Management UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a global app-shell + a **Manage** area with three owner-scoped registry screens — Secrets (write-only values), Skills, and MCP servers — over the existing `capabilities` API. Frontend-only.

**Architecture:** A global `AppLayout` (header with nav + the existing `NotificationBell`) wraps all routes; a nested `ManageLayout` (sidebar) hosts the registry screens. Each screen is a React Query list + dialogs over a new `lib/api/capabilities.ts` data module, reusing small shared `ResourceTable`/`ConfirmDialog` components. No backend changes.

**Tech Stack:** React 18 + TypeScript + Vite + Tailwind, `@tanstack/react-query`, `react-router-dom` (data router), Vitest + Testing Library + MSW. Spec: `docs/specs/2026-06-14-c1a-capability-management-ui-design.md`. All UI commands run from `ui/`.

---

## Conventions (read once)

- **API base is `/api`** — every fetch path and every MSW handler uses `/api/...`.
- Client helpers in `ui/src/lib/api/client.ts` already exist: `apiGet`, `apiGetPage`, `apiPost`, `apiPatch`, `apiDelete` (envelope-aware; throw `ApiError`).
- Data modules export a `*Keys` factory + typed fns (see `lib/api/projects.ts`). Hooks: `useQuery({queryKey, queryFn})` for lists; `useMutation({mutationFn, onSuccess: () => qc.invalidateQueries({queryKey})})` for writes (see `useProjects.ts`/`useCreateProject.ts`).
- Tests: inline `QueryClientProvider` (`retry:false`) + `MemoryRouter`; per-test `server.use(http.…("/api/…"))`; `onUnhandledRequest: "error"` (so any endpoint a rendered component calls **must** be mocked). MSW server in `ui/src/test/server.ts`, default handlers in `ui/src/test/handlers.ts`.
- Commands: `npm test` (vitest run), `npm run lint` (`tsc --noEmit`), `npm run build` (`tsc -b && vite build`). Run a single file: `npx vitest run src/features/manage/SecretsPage.test.tsx`.

## File Structure

- `ui/src/lib/api/client.ts` — **modify**: add `apiPut`.
- `ui/src/lib/api/types.ts` — **modify**: add `Secret`, `Skill`, `McpServer`.
- `ui/src/lib/api/capabilities.ts` — **create**: keys + fns for secrets/skills/mcpServers.
- `ui/src/features/components/ResourceTable.tsx` — **create**.
- `ui/src/features/components/ConfirmDialog.tsx` — **create**.
- `ui/src/app/AppLayout.tsx` — **create**: global header + `<Outlet/>`.
- `ui/src/app/router.tsx` — **modify**: export `routes`; wrap in `AppLayout`; add `/manage/*`.
- `ui/src/features/board/BoardPage.tsx` — **modify**: drop the inline `NotificationBell`; `h-screen` → `h-full`.
- `ui/src/test/handlers.ts` — **modify**: default notification handlers (so global-header renders don't error).
- `ui/src/features/manage/ManageLayout.tsx`, `SecretsPage.tsx`, `SetSecretValueDialog.tsx`, `SkillsPage.tsx`, `McpServersPage.tsx` + `useSecrets.ts`/`useSkills.ts`/`useMcpServers.ts` + `*.test.tsx` — **create**.

---

## Task 1: Data layer — `apiPut`, capability types, `capabilities.ts`

**Files:**
- Modify: `ui/src/lib/api/client.ts`
- Modify: `ui/src/lib/api/types.ts`
- Create: `ui/src/lib/api/capabilities.ts`
- Test: `ui/src/lib/api/capabilities.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// ui/src/lib/api/capabilities.test.ts
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { listSecrets, setSecretValue, createSkill, listMcpServers } from "./capabilities";

test("listSecrets unwraps the envelope and never includes a value", async () => {
  server.use(
    http.get("/api/secrets", () =>
      HttpResponse.json({
        success: true,
        data: [{ id: "s1", owner_id: "u", name: "GITHUB_TOKEN", description: "", has_value: true, created_at: "2026-01-01T00:00:00Z" }],
        error: null,
        meta: { total: 1, page_size: 200, page_number: 1 },
      }),
    ),
  );
  const secrets = await listSecrets();
  expect(secrets[0].name).toBe("GITHUB_TOKEN");
  expect(secrets[0].has_value).toBe(true);
  expect("value" in secrets[0]).toBe(false);
});

test("setSecretValue PUTs the value and returns the updated secret", async () => {
  let sentBody: unknown = null;
  server.use(
    http.put("/api/secrets/s1/value", async ({ request }) => {
      sentBody = await request.json();
      return HttpResponse.json({
        success: true,
        data: { id: "s1", owner_id: "u", name: "GITHUB_TOKEN", description: "", has_value: true, created_at: "2026-01-01T00:00:00Z" },
        error: null,
      });
    }),
  );
  const updated = await setSecretValue("s1", "ghp_secret");
  expect(sentBody).toEqual({ value: "ghp_secret" });
  expect(updated.has_value).toBe(true);
});

test("createSkill POSTs to /api/skills", async () => {
  server.use(
    http.post("/api/skills", async ({ request }) => {
      const body = (await request.json()) as { name: string };
      return HttpResponse.json({ success: true, data: { id: "k1", owner_id: "u", name: body.name, description: "", source: "", created_at: "2026-01-01T00:00:00Z" }, error: null }, { status: 201 });
    }),
  );
  const skill = await createSkill({ name: "search" });
  expect(skill.id).toBe("k1");
});

test("listMcpServers returns the registry rows", async () => {
  server.use(
    http.get("/api/mcp-servers", () =>
      HttpResponse.json({ success: true, data: [{ id: "m1", owner_id: "u", name: "github", transport: "stdio", command_or_url: "npx ...", tool_allowlist: ["mcp__github__search"], created_at: "2026-01-01T00:00:00Z" }], error: null, meta: { total: 1, page_size: 200, page_number: 1 } }),
    ),
  );
  const servers = await listMcpServers();
  expect(servers[0].tool_allowlist).toEqual(["mcp__github__search"]);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npx vitest run src/lib/api/capabilities.test.ts`
Expected: FAIL — `./capabilities` module not found.

- [ ] **Step 3: Add `apiPut` to `client.ts`**

Append after `apiPatch` in `ui/src/lib/api/client.ts`:

```ts
export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  return (await request<T>(path, { method: "PUT", body: JSON.stringify(body) })).data as T;
}
```

- [ ] **Step 4: Add types to `types.ts`**

Append to `ui/src/lib/api/types.ts`:

```ts
export interface Secret {
  id: string;
  owner_id: string;
  name: string;
  description: string;
  has_value: boolean;
  created_at: string;
}

export interface Skill {
  id: string;
  owner_id: string;
  name: string;
  description: string;
  source: string;
  created_at: string;
}

export type McpTransport = "stdio" | "http";

export interface McpServer {
  id: string;
  owner_id: string;
  name: string;
  transport: McpTransport;
  command_or_url: string;
  tool_allowlist: string[];
  created_at: string;
}
```

- [ ] **Step 5: Create `capabilities.ts`**

```ts
// ui/src/lib/api/capabilities.ts
import { apiDelete, apiGetPage, apiPatch, apiPost, apiPut } from "./client";
import type { McpServer, McpTransport, Secret, Skill } from "./types";

// ---- Secrets (write-only values) ----
export const secretKeys = { all: ["secrets"] as const };

export interface CreateSecretInput { name: string; description?: string }
export interface UpdateSecretInput { name?: string; description?: string }

export async function listSecrets(): Promise<Secret[]> {
  return (await apiGetPage<Secret[]>("/secrets?page_size=200")).data;
}
export async function createSecret(input: CreateSecretInput): Promise<Secret> {
  return apiPost<Secret>("/secrets", input);
}
export async function updateSecret(id: string, input: UpdateSecretInput): Promise<Secret> {
  return apiPatch<Secret>(`/secrets/${id}`, input);
}
export async function setSecretValue(id: string, value: string): Promise<Secret> {
  return apiPut<Secret>(`/secrets/${id}/value`, { value });
}
export async function deleteSecret(id: string): Promise<{ deleted: string }> {
  return apiDelete<{ deleted: string }>(`/secrets/${id}`);
}

// ---- Skills ----
export const skillKeys = { all: ["skills"] as const };

export interface CreateSkillInput { name: string; description?: string; source?: string }
export interface UpdateSkillInput { name?: string; description?: string; source?: string }

export async function listSkills(): Promise<Skill[]> {
  return (await apiGetPage<Skill[]>("/skills?page_size=200")).data;
}
export async function createSkill(input: CreateSkillInput): Promise<Skill> {
  return apiPost<Skill>("/skills", input);
}
export async function updateSkill(id: string, input: UpdateSkillInput): Promise<Skill> {
  return apiPatch<Skill>(`/skills/${id}`, input);
}
export async function deleteSkill(id: string): Promise<{ deleted: string }> {
  return apiDelete<{ deleted: string }>(`/skills/${id}`);
}

// ---- MCP servers ----
export const mcpServerKeys = { all: ["mcp-servers"] as const };

export interface CreateMcpServerInput { name: string; transport: McpTransport; command_or_url: string; tool_allowlist: string[] }
export interface UpdateMcpServerInput { name?: string; transport?: McpTransport; command_or_url?: string; tool_allowlist?: string[] }

export async function listMcpServers(): Promise<McpServer[]> {
  return (await apiGetPage<McpServer[]>("/mcp-servers?page_size=200")).data;
}
export async function createMcpServer(input: CreateMcpServerInput): Promise<McpServer> {
  return apiPost<McpServer>("/mcp-servers", input);
}
export async function updateMcpServer(id: string, input: UpdateMcpServerInput): Promise<McpServer> {
  return apiPatch<McpServer>(`/mcp-servers/${id}`, input);
}
export async function deleteMcpServer(id: string): Promise<{ deleted: string }> {
  return apiDelete<{ deleted: string }>(`/mcp-servers/${id}`);
}
```

- [ ] **Step 6: Run test + lint**

Run: `cd ui && npx vitest run src/lib/api/capabilities.test.ts && npm run lint`
Expected: PASS (4 tests); tsc clean.

- [ ] **Step 7: Commit**

```bash
git add ui/src/lib/api/client.ts ui/src/lib/api/types.ts ui/src/lib/api/capabilities.ts ui/src/lib/api/capabilities.test.ts
git commit -m "feat(ui): capabilities api module + apiPut + registry types"
```

---

## Task 2: Shared components — `ResourceTable` + `ConfirmDialog`

**Files:**
- Create: `ui/src/features/components/ResourceTable.tsx`
- Create: `ui/src/features/components/ConfirmDialog.tsx`
- Test: `ui/src/features/components/ResourceTable.test.tsx`, `ConfirmDialog.test.tsx`

- [ ] **Step 1: Write the failing tests**

```tsx
// ui/src/features/components/ResourceTable.test.tsx
import { render, screen } from "@testing-library/react";
import { ResourceTable } from "./ResourceTable";

test("renders rows via column renderers, and an empty message when no rows", () => {
  const { rerender } = render(
    <ResourceTable
      rows={[{ id: "a", name: "Alpha" }]}
      rowKey={(r) => r.id}
      columns={[{ header: "Name", render: (r) => r.name }]}
      actions={(r) => <button>edit {r.name}</button>}
    />,
  );
  expect(screen.getByText("Alpha")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "edit Alpha" })).toBeInTheDocument();

  rerender(
    <ResourceTable rows={[]} rowKey={(r: { id: string }) => r.id} columns={[{ header: "Name", render: () => null }]} empty="Nothing yet" />,
  );
  expect(screen.getByText("Nothing yet")).toBeInTheDocument();
});
```

```tsx
// ui/src/features/components/ConfirmDialog.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConfirmDialog } from "./ConfirmDialog";

test("confirms and cancels", async () => {
  const onConfirm = vi.fn();
  const onClose = vi.fn();
  render(<ConfirmDialog title="Delete?" message="Sure?" onConfirm={onConfirm} onClose={onClose} />);
  await userEvent.click(screen.getByRole("button", { name: /delete/i }));
  expect(onConfirm).toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
  expect(onClose).toHaveBeenCalled();
});
```

- [ ] **Step 2: Run to verify fail**

Run: `cd ui && npx vitest run src/features/components/`
Expected: FAIL — modules not found.

- [ ] **Step 3: Implement the components**

```tsx
// ui/src/features/components/ResourceTable.tsx
import type { ReactNode } from "react";

export interface Column<T> {
  header: string;
  render: (row: T) => ReactNode;
}

interface ResourceTableProps<T> {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  actions?: (row: T) => ReactNode;
  empty?: string;
}

export function ResourceTable<T>({ rows, columns, rowKey, actions, empty }: ResourceTableProps<T>) {
  if (rows.length === 0) {
    return <p className="text-sm text-gray-500">{empty ?? "Nothing here yet."}</p>;
  }
  return (
    <table className="w-full text-left text-sm">
      <thead className="border-b text-xs uppercase text-gray-500">
        <tr>
          {columns.map((c) => (
            <th key={c.header} className="py-2 pr-4 font-semibold">{c.header}</th>
          ))}
          {actions && <th className="py-2" />}
        </tr>
      </thead>
      <tbody className="divide-y">
        {rows.map((row) => (
          <tr key={rowKey(row)}>
            {columns.map((c) => (
              <td key={c.header} className="py-2 pr-4 align-top">{c.render(row)}</td>
            ))}
            {actions && <td className="py-2 text-right">{actions(row)}</td>}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

```tsx
// ui/src/features/components/ConfirmDialog.tsx
interface ConfirmDialogProps {
  title: string;
  message: string;
  confirmLabel?: string;
  pending?: boolean;
  error?: string;
  onConfirm: () => void | Promise<void>;
  onClose: () => void;
}

export function ConfirmDialog({ title, message, confirmLabel = "Delete", pending, error, onConfirm, onClose }: ConfirmDialogProps) {
  return (
    <div className="fixed inset-0 grid place-items-center bg-black/30">
      <div className="w-96 space-y-3 rounded bg-white p-4 shadow">
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="text-sm text-gray-600">{message}</p>
        {error && <p className="text-xs text-red-600">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded px-3 py-1 text-sm">Cancel</button>
          <button
            type="button"
            disabled={pending}
            onClick={() => void onConfirm()}
            className="rounded bg-red-600 px-3 py-1 text-sm text-white disabled:opacity-50"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests + lint**

Run: `cd ui && npx vitest run src/features/components/ && npm run lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/features/components/
git commit -m "feat(ui): shared ResourceTable + ConfirmDialog"
```

---

## Task 3: App shell, Manage layout, routing (move the bell)

**Files:**
- Create: `ui/src/app/AppLayout.tsx`
- Create: `ui/src/features/manage/ManageLayout.tsx`
- Modify: `ui/src/app/router.tsx`
- Modify: `ui/src/features/board/BoardPage.tsx`
- Modify: `ui/src/test/handlers.ts`
- Test: `ui/src/app/AppLayout.test.tsx`

- [ ] **Step 1: Add default notification handlers** (so any render of the global header doesn't hit `onUnhandledRequest: "error"`).

In `ui/src/test/handlers.ts`, add to the `handlers` array:

```ts
  http.get("/api/notifications/unread-count", () =>
    HttpResponse.json({ success: true, data: { count: 0 }, error: null }),
  ),
  http.get("/api/notifications", () =>
    HttpResponse.json({ success: true, data: [], error: null, meta: { total: 0, page_size: 50, page_number: 1 } }),
  ),
```

- [ ] **Step 2: Write the failing routing test**

```tsx
// ui/src/app/AppLayout.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { routes } from "./router";

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(
    <QueryClientProvider client={qc}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

test("header shows nav + bell, and Manage routes to the secrets screen", async () => {
  renderAt("/");
  expect(screen.getByRole("link", { name: /projects/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /manage/i })).toBeInTheDocument();
  expect(screen.getByLabelText(/unread notifications/i)).toBeInTheDocument();

  await userEvent.click(screen.getByRole("link", { name: /manage/i }));
  // ManageLayout sidebar + Secrets screen heading
  expect(await screen.findByRole("heading", { name: /secrets/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /mcp servers/i })).toBeInTheDocument();
});
```

- [ ] **Step 3: Run to verify fail**

Run: `cd ui && npx vitest run src/app/AppLayout.test.tsx`
Expected: FAIL — `routes` not exported / `AppLayout` missing.

- [ ] **Step 4: Create `AppLayout.tsx`**

```tsx
// ui/src/app/AppLayout.tsx
import { NavLink, Outlet } from "react-router-dom";
import { NotificationBell } from "../features/notifications/NotificationBell";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `text-sm ${isActive ? "font-semibold text-blue-700" : "text-gray-600 hover:text-gray-900"}`;

export function AppLayout() {
  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center gap-4 border-b px-4 py-2">
        <NavLink to="/" className="text-sm font-bold">yaah</NavLink>
        <nav className="flex gap-4">
          <NavLink to="/" end className={linkClass}>Projects</NavLink>
          <NavLink to="/manage" className={linkClass}>Manage</NavLink>
        </nav>
        <div className="ml-auto">
          <NotificationBell />
        </div>
      </header>
      <main className="min-h-0 flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
```

- [ ] **Step 5: Create `ManageLayout.tsx`**

```tsx
// ui/src/features/manage/ManageLayout.tsx
import { NavLink, Outlet } from "react-router-dom";

const items = [
  { to: "/manage/secrets", label: "Secrets" },
  { to: "/manage/skills", label: "Skills" },
  { to: "/manage/mcp-servers", label: "MCP servers" },
];

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `block rounded px-3 py-2 text-sm ${isActive ? "bg-blue-50 font-medium text-blue-700" : "text-gray-700 hover:bg-gray-50"}`;

export function ManageLayout() {
  return (
    <div className="flex h-full">
      <aside className="w-48 shrink-0 border-r p-3">
        <nav className="space-y-1">
          {items.map((i) => (
            <NavLink key={i.to} to={i.to} className={linkClass}>{i.label}</NavLink>
          ))}
        </nav>
      </aside>
      <section className="flex-1 overflow-auto p-6">
        <Outlet />
      </section>
    </div>
  );
}
```

- [ ] **Step 6: Rewrite `router.tsx`** to export `routes` and nest everything under `AppLayout`:

```tsx
// ui/src/app/router.tsx
import { createBrowserRouter, Navigate, type RouteObject } from "react-router-dom";
import { AppLayout } from "./AppLayout";
import ProjectsPage from "../features/projects/ProjectsPage";
import BoardPage from "../features/board/BoardPage";
import { ManageLayout } from "../features/manage/ManageLayout";
import { SecretsPage } from "../features/manage/SecretsPage";
import { SkillsPage } from "../features/manage/SkillsPage";
import { McpServersPage } from "../features/manage/McpServersPage";

export const routes: RouteObject[] = [
  {
    element: <AppLayout />,
    children: [
      { path: "/", element: <ProjectsPage /> },
      { path: "/projects/:projectId", element: <BoardPage /> },
      {
        path: "/manage",
        element: <ManageLayout />,
        children: [
          { index: true, element: <Navigate to="secrets" replace /> },
          { path: "secrets", element: <SecretsPage /> },
          { path: "skills", element: <SkillsPage /> },
          { path: "mcp-servers", element: <McpServersPage /> },
        ],
      },
    ],
  },
];

export const router = createBrowserRouter(routes);
```

> The `Secrets`/`Skills`/`McpServers` page imports resolve in Tasks 4–6. To keep this task's test green now, create **stub** files first (replaced in later tasks):
> `SecretsPage.tsx` → `export function SecretsPage() { return <h1 className="text-xl font-semibold">Secrets</h1>; }`
> `SkillsPage.tsx` → `export function SkillsPage() { return <h1 className="text-xl font-semibold">Skills</h1>; }`
> `McpServersPage.tsx` → `export function McpServersPage() { return <h1 className="text-xl font-semibold">MCP servers</h1>; }`

- [ ] **Step 7: Update `BoardPage.tsx`** — remove the bell (now global) and fix height. In `ui/src/features/board/BoardPage.tsx`:
  - Delete the import line `import { NotificationBell } from "../notifications/NotificationBell";`.
  - Delete the `<div className="ml-auto"><NotificationBell /></div>` block from its header.
  - Change the outer `<div className="flex h-screen flex-col">` to `<div className="flex h-full flex-col">` (it now lives inside `AppLayout`'s `main`).

- [ ] **Step 8: Run test + full UI suite + lint**

Run: `cd ui && npx vitest run src/app/AppLayout.test.tsx && npm test && npm run lint`
Expected: AppLayout test PASS; full suite PASS (existing board/projects/notifications tests still green — the bell moved but still renders); tsc clean.

- [ ] **Step 9: Commit**

```bash
git add ui/src/app/ ui/src/features/manage/ManageLayout.tsx ui/src/features/manage/SecretsPage.tsx ui/src/features/manage/SkillsPage.tsx ui/src/features/manage/McpServersPage.tsx ui/src/features/board/BoardPage.tsx ui/src/test/handlers.ts
git commit -m "feat(ui): AppLayout shell + Manage sidebar + routing; move bell to header"
```

---

## Task 4: Secrets screen (full)

**Files:**
- Create: `ui/src/features/manage/useSecrets.ts`
- Replace: `ui/src/features/manage/SecretsPage.tsx` (stub → full)
- Create: `ui/src/features/manage/SetSecretValueDialog.tsx`
- Test: `ui/src/features/manage/SecretsPage.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// ui/src/features/manage/SecretsPage.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { SecretsPage } from "./SecretsPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><SecretsPage /></MemoryRouter>
    </QueryClientProvider>,
  );
}

const seed = (has_value: boolean) => [
  { id: "s1", owner_id: "u", name: "GITHUB_TOKEN", description: "", has_value, created_at: "2026-01-01T00:00:00Z" },
];

test("lists secrets with status badge and creates one", async () => {
  const rows = seed(false);
  server.use(
    http.get("/api/secrets", () => HttpResponse.json({ success: true, data: rows, error: null, meta: { total: rows.length, page_size: 200, page_number: 1 } })),
    http.post("/api/secrets", async ({ request }) => {
      const b = (await request.json()) as { name: string };
      const created = { id: "s2", owner_id: "u", name: b.name, description: "", has_value: false, created_at: "2026-01-02T00:00:00Z" };
      rows.push(created);
      return HttpResponse.json({ success: true, data: created, error: null }, { status: 201 });
    }),
  );
  renderPage();
  expect(await screen.findByText("GITHUB_TOKEN")).toBeInTheDocument();
  expect(screen.getByText(/empty/i)).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: /new secret/i }));
  await userEvent.type(screen.getByLabelText(/name/i), "OPENAI_KEY");
  await userEvent.click(screen.getByRole("button", { name: /^create$/i }));
  await waitFor(() => expect(screen.getByText("OPENAI_KEY")).toBeInTheDocument());
});

test("set value submits the value and never renders it back", async () => {
  const rows = seed(false);
  server.use(
    http.get("/api/secrets", () => HttpResponse.json({ success: true, data: rows, error: null, meta: { total: rows.length, page_size: 200, page_number: 1 } })),
    http.put("/api/secrets/s1/value", async () => {
      rows[0] = { ...rows[0], has_value: true };
      return HttpResponse.json({ success: true, data: rows[0], error: null });
    }),
  );
  renderPage();
  await screen.findByText("GITHUB_TOKEN");
  await userEvent.click(screen.getByRole("button", { name: /set value/i }));
  const input = screen.getByLabelText(/value/i);
  await userEvent.type(input, "ghp_supersecret");
  await userEvent.click(screen.getByRole("button", { name: /save/i }));
  await waitFor(() => expect(screen.getByText(/set/i)).toBeInTheDocument());
  // the secret value must not be anywhere in the DOM afterwards
  expect(screen.queryByText(/ghp_supersecret/)).not.toBeInTheDocument();
  expect(document.body.innerHTML).not.toContain("ghp_supersecret");
});
```

- [ ] **Step 2: Run to verify fail**

Run: `cd ui && npx vitest run src/features/manage/SecretsPage.test.tsx`
Expected: FAIL (stub page has no list/buttons).

- [ ] **Step 3: Create `useSecrets.ts`**

```tsx
// ui/src/features/manage/useSecrets.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createSecret, deleteSecret, listSecrets, secretKeys, setSecretValue, updateSecret,
  type CreateSecretInput, type UpdateSecretInput,
} from "../../lib/api/capabilities";

export function useSecrets() {
  return useQuery({ queryKey: secretKeys.all, queryFn: listSecrets });
}

function useInvalidate() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: secretKeys.all });
}

export function useCreateSecret() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (i: CreateSecretInput) => createSecret(i), onSuccess: invalidate });
}
export function useUpdateSecret() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (a: { id: string; input: UpdateSecretInput }) => updateSecret(a.id, a.input), onSuccess: invalidate });
}
export function useSetSecretValue() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (a: { id: string; value: string }) => setSecretValue(a.id, a.value), onSuccess: invalidate });
}
export function useDeleteSecret() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (id: string) => deleteSecret(id), onSuccess: invalidate });
}
```

- [ ] **Step 4: Create `SetSecretValueDialog.tsx`**

```tsx
// ui/src/features/manage/SetSecretValueDialog.tsx
import { useState } from "react";
import { useSetSecretValue } from "./useSecrets";

export function SetSecretValueDialog({ secretId, secretName, onClose }: { secretId: string; secretName: string; onClose: () => void }) {
  const [value, setValue] = useState("");
  const setVal = useSetSecretValue();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (value === "") return;
    try {
      await setVal.mutateAsync({ id: secretId, value });
      setValue(""); // clear the secret from state immediately on success
      onClose();
    } catch {
      setValue(""); // never retain the value, even on error
    }
  }

  const is503 = (setVal.error as { status?: number } | null)?.status === 503;

  return (
    <div className="fixed inset-0 grid place-items-center bg-black/30">
      <form onSubmit={submit} className="w-96 space-y-3 rounded bg-white p-4 shadow">
        <h2 className="text-lg font-semibold">Set value — {secretName}</h2>
        <label className="block text-sm">
          Value
          <input type="password" autoComplete="off" className="mt-1 w-full rounded border p-2" value={value} onChange={(e) => setValue(e.target.value)} />
        </label>
        <p className="text-xs text-gray-500">The value is write-only — it is stored encrypted and never shown again.</p>
        {setVal.isError && (
          <p className="text-xs text-red-600">
            {is503 ? "Secret encryption key not configured on the server." : (setVal.error as Error).message}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded px-3 py-1 text-sm">Cancel</button>
          <button type="submit" disabled={value === "" || setVal.isPending} className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50">Save</button>
        </div>
      </form>
    </div>
  );
}
```

- [ ] **Step 5: Replace `SecretsPage.tsx`** (stub → full)

```tsx
// ui/src/features/manage/SecretsPage.tsx
import { useState } from "react";
import type { Secret } from "../../lib/api/types";
import { ResourceTable } from "../components/ResourceTable";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useCreateSecret, useDeleteSecret, useSecrets } from "./useSecrets";
import { SetSecretValueDialog } from "./SetSecretValueDialog";

export function SecretsPage() {
  const { data = [], isLoading, isError, error } = useSecrets();
  const create = useCreateSecret();
  const del = useDeleteSecret();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [valueFor, setValueFor] = useState<Secret | null>(null);
  const [deleting, setDeleting] = useState<Secret | null>(null);

  async function submitCreate(e: React.FormEvent) {
    e.preventDefault();
    if (name.trim() === "") return;
    await create.mutateAsync({ name: name.trim(), description: description.trim() });
    setName(""); setDescription(""); setCreating(false);
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Secrets</h1>
        <button onClick={() => setCreating(true)} className="rounded bg-blue-600 px-3 py-1 text-sm text-white">New secret</button>
      </div>
      {isLoading && <p className="text-sm text-gray-500">Loading…</p>}
      {isError && <p className="text-sm text-red-600">{(error as Error).message}</p>}
      <ResourceTable
        rows={data}
        rowKey={(s) => s.id}
        empty="No secrets yet."
        columns={[
          { header: "Name", render: (s) => <span className="font-medium">{s.name}</span> },
          { header: "Description", render: (s) => <span className="text-gray-600">{s.description}</span> },
          { header: "Status", render: (s) => (s.has_value ? <span className="text-green-700">● set</span> : <span className="text-gray-400">○ empty</span>) },
        ]}
        actions={(s) => (
          <div className="flex justify-end gap-2 text-sm">
            <button onClick={() => setValueFor(s)} className="text-blue-700">Set value</button>
            <button onClick={() => setDeleting(s)} className="text-red-600">Delete</button>
          </div>
        )}
      />

      {creating && (
        <div className="fixed inset-0 grid place-items-center bg-black/30">
          <form onSubmit={submitCreate} className="w-96 space-y-3 rounded bg-white p-4 shadow">
            <h2 className="text-lg font-semibold">New secret</h2>
            <label className="block text-sm">Name<input className="mt-1 w-full rounded border p-2" value={name} onChange={(e) => setName(e.target.value)} /></label>
            <label className="block text-sm">Description<input className="mt-1 w-full rounded border p-2" value={description} onChange={(e) => setDescription(e.target.value)} /></label>
            {create.isError && <p className="text-xs text-red-600">{(create.error as Error).message}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setCreating(false)} className="rounded px-3 py-1 text-sm">Cancel</button>
              <button type="submit" disabled={name.trim() === "" || create.isPending} className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50">Create</button>
            </div>
          </form>
        </div>
      )}

      {valueFor && <SetSecretValueDialog secretId={valueFor.id} secretName={valueFor.name} onClose={() => setValueFor(null)} />}

      {deleting && (
        <ConfirmDialog
          title="Delete secret"
          message={`Delete "${deleting.name}"? This cannot be undone.`}
          pending={del.isPending}
          error={del.isError ? (del.error as Error).message : undefined}
          onConfirm={async () => { await del.mutateAsync(deleting.id); setDeleting(null); }}
          onClose={() => setDeleting(null)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 6: Run test + lint**

Run: `cd ui && npx vitest run src/features/manage/SecretsPage.test.tsx && npm run lint`
Expected: PASS (incl. the "value never rendered" assertion).

- [ ] **Step 7: Commit**

```bash
git add ui/src/features/manage/useSecrets.ts ui/src/features/manage/SecretsPage.tsx ui/src/features/manage/SetSecretValueDialog.tsx ui/src/features/manage/SecretsPage.test.tsx
git commit -m "feat(ui): secrets management screen (write-only set-value)"
```

---

## Task 5: Skills screen (full)

**Files:**
- Create: `ui/src/features/manage/useSkills.ts`
- Replace: `ui/src/features/manage/SkillsPage.tsx` (stub → full)
- Test: `ui/src/features/manage/SkillsPage.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// ui/src/features/manage/SkillsPage.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { SkillsPage } from "./SkillsPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter><SkillsPage /></MemoryRouter></QueryClientProvider>);
}

test("lists, creates, and deletes a skill", async () => {
  const rows = [{ id: "k1", owner_id: "u", name: "code-search", description: "grep/AST", source: "builtin", created_at: "2026-01-01T00:00:00Z" }];
  server.use(
    http.get("/api/skills", () => HttpResponse.json({ success: true, data: rows, error: null, meta: { total: rows.length, page_size: 200, page_number: 1 } })),
    http.post("/api/skills", async ({ request }) => {
      const b = (await request.json()) as { name: string };
      const created = { id: "k2", owner_id: "u", name: b.name, description: "", source: "", created_at: "2026-01-02T00:00:00Z" };
      rows.push(created);
      return HttpResponse.json({ success: true, data: created, error: null }, { status: 201 });
    }),
    http.delete("/api/skills/k1", () => { rows.splice(0, 1); return HttpResponse.json({ success: true, data: { deleted: "k1" }, error: null }); }),
  );
  renderPage();
  expect(await screen.findByText("code-search")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: /new skill/i }));
  await userEvent.type(screen.getByLabelText(/name/i), "rag-query");
  await userEvent.click(screen.getByRole("button", { name: /^create$/i }));
  await waitFor(() => expect(screen.getByText("rag-query")).toBeInTheDocument());

  await userEvent.click(screen.getAllByRole("button", { name: /delete/i })[0]);
  await userEvent.click(screen.getByRole("button", { name: /^delete$/i })); // confirm
  await waitFor(() => expect(screen.queryByText("code-search")).not.toBeInTheDocument());
});
```

- [ ] **Step 2: Run to verify fail**

Run: `cd ui && npx vitest run src/features/manage/SkillsPage.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Create `useSkills.ts`**

```tsx
// ui/src/features/manage/useSkills.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createSkill, deleteSkill, listSkills, skillKeys, updateSkill,
  type CreateSkillInput, type UpdateSkillInput,
} from "../../lib/api/capabilities";

export function useSkills() {
  return useQuery({ queryKey: skillKeys.all, queryFn: listSkills });
}
function useInvalidate() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: skillKeys.all });
}
export function useCreateSkill() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (i: CreateSkillInput) => createSkill(i), onSuccess: invalidate });
}
export function useUpdateSkill() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (a: { id: string; input: UpdateSkillInput }) => updateSkill(a.id, a.input), onSuccess: invalidate });
}
export function useDeleteSkill() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (id: string) => deleteSkill(id), onSuccess: invalidate });
}
```

- [ ] **Step 4: Replace `SkillsPage.tsx`**

```tsx
// ui/src/features/manage/SkillsPage.tsx
import { useState } from "react";
import type { Skill } from "../../lib/api/types";
import { ResourceTable } from "../components/ResourceTable";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useCreateSkill, useDeleteSkill, useSkills, useUpdateSkill } from "./useSkills";

interface Draft { name: string; description: string; source: string }
const EMPTY: Draft = { name: "", description: "", source: "" };

export function SkillsPage() {
  const { data = [], isLoading, isError, error } = useSkills();
  const create = useCreateSkill();
  const update = useUpdateSkill();
  const del = useDeleteSkill();
  const [editing, setEditing] = useState<Skill | "new" | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [deleting, setDeleting] = useState<Skill | null>(null);

  function openNew() { setDraft(EMPTY); setEditing("new"); }
  function openEdit(s: Skill) { setDraft({ name: s.name, description: s.description, source: s.source }); setEditing(s); }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (draft.name.trim() === "") return;
    if (editing === "new") await create.mutateAsync(draft);
    else if (editing) await update.mutateAsync({ id: editing.id, input: draft });
    setEditing(null);
  }

  const mutating = create.isPending || update.isPending;
  const mutError = (create.error || update.error) as Error | null;

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Skills</h1>
        <button onClick={openNew} className="rounded bg-blue-600 px-3 py-1 text-sm text-white">New skill</button>
      </div>
      {isLoading && <p className="text-sm text-gray-500">Loading…</p>}
      {isError && <p className="text-sm text-red-600">{(error as Error).message}</p>}
      <ResourceTable
        rows={data}
        rowKey={(s) => s.id}
        empty="No skills yet."
        columns={[
          { header: "Name", render: (s) => <span className="font-medium">{s.name}</span> },
          { header: "Description", render: (s) => <span className="text-gray-600">{s.description}</span> },
          { header: "Source", render: (s) => <span className="text-gray-600">{s.source}</span> },
        ]}
        actions={(s) => (
          <div className="flex justify-end gap-2 text-sm">
            <button onClick={() => openEdit(s)} className="text-blue-700">Edit</button>
            <button onClick={() => setDeleting(s)} className="text-red-600">Delete</button>
          </div>
        )}
      />

      {editing && (
        <div className="fixed inset-0 grid place-items-center bg-black/30">
          <form onSubmit={submit} className="w-96 space-y-3 rounded bg-white p-4 shadow">
            <h2 className="text-lg font-semibold">{editing === "new" ? "New skill" : "Edit skill"}</h2>
            <label className="block text-sm">Name<input className="mt-1 w-full rounded border p-2" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></label>
            <label className="block text-sm">Description<input className="mt-1 w-full rounded border p-2" value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></label>
            <label className="block text-sm">Source<input className="mt-1 w-full rounded border p-2" value={draft.source} onChange={(e) => setDraft({ ...draft, source: e.target.value })} /></label>
            {mutError && <p className="text-xs text-red-600">{mutError.message}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setEditing(null)} className="rounded px-3 py-1 text-sm">Cancel</button>
              <button type="submit" disabled={draft.name.trim() === "" || mutating} className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50">{editing === "new" ? "Create" : "Save"}</button>
            </div>
          </form>
        </div>
      )}

      {deleting && (
        <ConfirmDialog
          title="Delete skill"
          message={`Delete "${deleting.name}"?`}
          pending={del.isPending}
          error={del.isError ? (del.error as Error).message : undefined}
          onConfirm={async () => { await del.mutateAsync(deleting.id); setDeleting(null); }}
          onClose={() => setDeleting(null)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 5: Run test + lint**

Run: `cd ui && npx vitest run src/features/manage/SkillsPage.test.tsx && npm run lint`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ui/src/features/manage/useSkills.ts ui/src/features/manage/SkillsPage.tsx ui/src/features/manage/SkillsPage.test.tsx
git commit -m "feat(ui): skills registry screen"
```

---

## Task 6: MCP servers screen (full, with tool-allowlist chip editor)

**Files:**
- Create: `ui/src/features/manage/useMcpServers.ts`
- Replace: `ui/src/features/manage/McpServersPage.tsx` (stub → full)
- Test: `ui/src/features/manage/McpServersPage.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// ui/src/features/manage/McpServersPage.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { McpServersPage } from "./McpServersPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter><McpServersPage /></MemoryRouter></QueryClientProvider>);
}

test("lists and creates an MCP server with a tool-allowlist chip", async () => {
  const rows: unknown[] = [];
  let posted: { tool_allowlist: string[] } | null = null;
  server.use(
    http.get("/api/mcp-servers", () => HttpResponse.json({ success: true, data: rows, error: null, meta: { total: rows.length, page_size: 200, page_number: 1 } })),
    http.post("/api/mcp-servers", async ({ request }) => {
      posted = (await request.json()) as { tool_allowlist: string[] };
      const created = { id: "m1", owner_id: "u", name: "github", transport: "stdio", command_or_url: "npx server", tool_allowlist: posted.tool_allowlist, created_at: "2026-01-02T00:00:00Z" };
      rows.push(created);
      return HttpResponse.json({ success: true, data: created, error: null }, { status: 201 });
    }),
  );
  renderPage();
  await waitFor(() => expect(screen.getByText(/no mcp servers/i)).toBeInTheDocument());

  await userEvent.click(screen.getByRole("button", { name: /new mcp server/i }));
  await userEvent.type(screen.getByLabelText(/name/i), "github");
  await userEvent.type(screen.getByLabelText(/command or url/i), "npx server");
  // add a tool to the allowlist
  const toolInput = screen.getByLabelText(/add tool/i);
  await userEvent.type(toolInput, "mcp__github__search{enter}");
  expect(screen.getByText("mcp__github__search")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /^create$/i }));

  await waitFor(() => expect(posted).toEqual(expect.objectContaining({ tool_allowlist: ["mcp__github__search"] })));
  await waitFor(() => expect(screen.getByText("github")).toBeInTheDocument());
});
```

- [ ] **Step 2: Run to verify fail**

Run: `cd ui && npx vitest run src/features/manage/McpServersPage.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Create `useMcpServers.ts`**

```tsx
// ui/src/features/manage/useMcpServers.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createMcpServer, deleteMcpServer, listMcpServers, mcpServerKeys, updateMcpServer,
  type CreateMcpServerInput, type UpdateMcpServerInput,
} from "../../lib/api/capabilities";

export function useMcpServers() {
  return useQuery({ queryKey: mcpServerKeys.all, queryFn: listMcpServers });
}
function useInvalidate() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: mcpServerKeys.all });
}
export function useCreateMcpServer() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (i: CreateMcpServerInput) => createMcpServer(i), onSuccess: invalidate });
}
export function useUpdateMcpServer() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (a: { id: string; input: UpdateMcpServerInput }) => updateMcpServer(a.id, a.input), onSuccess: invalidate });
}
export function useDeleteMcpServer() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (id: string) => deleteMcpServer(id), onSuccess: invalidate });
}
```

- [ ] **Step 4: Replace `McpServersPage.tsx`**

```tsx
// ui/src/features/manage/McpServersPage.tsx
import { useState } from "react";
import type { McpServer, McpTransport } from "../../lib/api/types";
import { ResourceTable } from "../components/ResourceTable";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useCreateMcpServer, useDeleteMcpServer, useMcpServers, useUpdateMcpServer } from "./useMcpServers";

interface Draft { name: string; transport: McpTransport; command_or_url: string; tool_allowlist: string[] }
const EMPTY: Draft = { name: "", transport: "stdio", command_or_url: "", tool_allowlist: [] };

export function McpServersPage() {
  const { data = [], isLoading, isError, error } = useMcpServers();
  const create = useCreateMcpServer();
  const update = useUpdateMcpServer();
  const del = useDeleteMcpServer();
  const [editing, setEditing] = useState<McpServer | "new" | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [tool, setTool] = useState("");
  const [deleting, setDeleting] = useState<McpServer | null>(null);

  function openNew() { setDraft(EMPTY); setTool(""); setEditing("new"); }
  function openEdit(s: McpServer) {
    setDraft({ name: s.name, transport: s.transport, command_or_url: s.command_or_url, tool_allowlist: [...s.tool_allowlist] });
    setTool(""); setEditing(s);
  }
  function addTool(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key !== "Enter") return;
    e.preventDefault();
    const t = tool.trim();
    if (t && !draft.tool_allowlist.includes(t)) setDraft({ ...draft, tool_allowlist: [...draft.tool_allowlist, t] });
    setTool("");
  }
  function removeTool(t: string) { setDraft({ ...draft, tool_allowlist: draft.tool_allowlist.filter((x) => x !== t) }); }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (draft.name.trim() === "") return;
    if (editing === "new") await create.mutateAsync(draft);
    else if (editing) await update.mutateAsync({ id: editing.id, input: draft });
    setEditing(null);
  }

  const mutating = create.isPending || update.isPending;
  const mutError = (create.error || update.error) as Error | null;

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">MCP servers</h1>
        <button onClick={openNew} className="rounded bg-blue-600 px-3 py-1 text-sm text-white">New MCP server</button>
      </div>
      {isLoading && <p className="text-sm text-gray-500">Loading…</p>}
      {isError && <p className="text-sm text-red-600">{(error as Error).message}</p>}
      <ResourceTable
        rows={data}
        rowKey={(s) => s.id}
        empty="No MCP servers yet."
        columns={[
          { header: "Name", render: (s) => <span className="font-medium">{s.name}</span> },
          { header: "Transport", render: (s) => <span className="text-gray-600">{s.transport}</span> },
          { header: "Command / URL", render: (s) => <span className="text-gray-600">{s.command_or_url}</span> },
          { header: "Tools", render: (s) => <span className="text-gray-600">{s.tool_allowlist.length}</span> },
        ]}
        actions={(s) => (
          <div className="flex justify-end gap-2 text-sm">
            <button onClick={() => openEdit(s)} className="text-blue-700">Edit</button>
            <button onClick={() => setDeleting(s)} className="text-red-600">Delete</button>
          </div>
        )}
      />

      {editing && (
        <div className="fixed inset-0 grid place-items-center bg-black/30">
          <form onSubmit={submit} className="w-[28rem] space-y-3 rounded bg-white p-4 shadow">
            <h2 className="text-lg font-semibold">{editing === "new" ? "New MCP server" : "Edit MCP server"}</h2>
            <label className="block text-sm">Name<input className="mt-1 w-full rounded border p-2" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></label>
            <label className="block text-sm">Transport
              <select className="mt-1 w-full rounded border p-2" value={draft.transport} onChange={(e) => setDraft({ ...draft, transport: e.target.value as McpTransport })}>
                <option value="stdio">stdio</option>
                <option value="http">http</option>
              </select>
            </label>
            <label className="block text-sm">Command or URL<input className="mt-1 w-full rounded border p-2" value={draft.command_or_url} onChange={(e) => setDraft({ ...draft, command_or_url: e.target.value })} /></label>
            <label className="block text-sm">Add tool
              <input className="mt-1 w-full rounded border p-2" placeholder="mcp__server__tool (Enter to add)" value={tool} onChange={(e) => setTool(e.target.value)} onKeyDown={addTool} />
            </label>
            <div className="flex flex-wrap gap-1">
              {draft.tool_allowlist.map((t) => (
                <span key={t} className="flex items-center gap-1 rounded bg-gray-100 px-2 py-0.5 text-xs">
                  {t}
                  <button type="button" aria-label={`remove ${t}`} onClick={() => removeTool(t)} className="text-gray-500">✕</button>
                </span>
              ))}
            </div>
            {mutError && <p className="text-xs text-red-600">{mutError.message}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setEditing(null)} className="rounded px-3 py-1 text-sm">Cancel</button>
              <button type="submit" disabled={draft.name.trim() === "" || mutating} className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50">{editing === "new" ? "Create" : "Save"}</button>
            </div>
          </form>
        </div>
      )}

      {deleting && (
        <ConfirmDialog
          title="Delete MCP server"
          message={`Delete "${deleting.name}"?`}
          pending={del.isPending}
          error={del.isError ? (del.error as Error).message : undefined}
          onConfirm={async () => { await del.mutateAsync(deleting.id); setDeleting(null); }}
          onClose={() => setDeleting(null)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 5: Run test + full suite + lint + build**

Run: `cd ui && npx vitest run src/features/manage/McpServersPage.test.tsx && npm test && npm run lint && npm run build`
Expected: target test PASS; full UI suite PASS; tsc clean; vite build succeeds.

- [ ] **Step 6: Commit**

```bash
git add ui/src/features/manage/useMcpServers.ts ui/src/features/manage/McpServersPage.tsx ui/src/features/manage/McpServersPage.test.tsx
git commit -m "feat(ui): MCP servers registry screen with tool-allowlist editor"
```

---

## Self-Review

**Spec coverage** (`docs/specs/2026-06-14-c1a-capability-management-ui-design.md`):
- §1/§5 app shell + Manage nav + routing → Task 3 (`AppLayout`, `ManageLayout`, `routes`).
- §2/§6.1 Secrets (list, create, write-only set-value, delete) → Task 4.
- §6.2 Skills (list/create/edit/delete) → Task 5.
- §6.3 MCP servers (list/create/edit/delete + tool-allowlist chips) → Task 6.
- §7 data layer (`apiPut`, types, `capabilities.ts`, hooks) → Tasks 1, 4–6.
- §2 move `NotificationBell` to global header → Task 3.
- §8 error handling (inline `ApiError.message`, secret 503 copy, confirm-before-delete, no value retained) → Tasks 2, 4.
- §9 testing (routing, secret value never rendered, per-screen CRUD, build/lint green) → per-task tests + Task 6 final `npm test`/`build`.

**Scope note / deviation:** the spec lists secret **metadata edit** (`PATCH /secrets/{id}`). The `updateSecret` fn is implemented (Task 1) and `useUpdateSecret` is wired (Task 4), but the Secrets screen ships create + set-value + delete only; a metadata-edit dialog is deferred as a trivial follow-up (identical shape to the Skills edit dialog). Flagged here so it's a conscious cut, not a gap. If desired, add it as a Task-4 follow-up step mirroring `SkillsPage`'s edit dialog.

**Placeholder scan:** none — every step has full code/commands. The three stub pages in Task 3 are explicitly replaced in Tasks 4–6 (called out in Task 3 Step 6).

**Type consistency:** `Secret`/`Skill`/`McpServer`/`McpTransport` (types.ts) match the `capabilities.ts` fns and the page props; `*Keys` names (`secretKeys`/`skillKeys`/`mcpServerKeys`) are consistent across hooks; mutation input types (`CreateSecretInput`, `CreateMcpServerInput`, …) match the api module. MSW paths all use the `/api` prefix. `ConfirmDialog`'s confirm button default label is `Delete`, which the Skills test selects via `name: /^delete$/i`.
