# yaah C1a — Capability & Governance Management UI (Design)

**Date:** 2026-06-14
**Status:** Approved design, pending implementation plan
**Phase:** C1a (management plane — first slice; part of Phase C in the yaah design)
**Depends on:** A2 (board UI + React/Vite/Tailwind + React Query + MSW conventions), A5c-1 (capability model: `Skill`/`McpServer`/`Secret` + `capabilities` API), A5c-3a (encrypted write-only secret values) — all merged to `main`.

## 1. Problem & goal

Phase C is the **management plane** (design §10): secrets UI, skills/MCP registries, model config + budgets, audit viewer, run inspector, autonomy dial, memory diff review. Almost all of these have backends already (`Secret`/`Skill`/`McpServer` + the `capabilities` API, `AuditEvent`, `UsageRecord`, `Notification`, LiteLLM), but **no management UI exists** — today you cannot add a secret, register a skill, or approve an MCP server without hitting the API or database by hand. The board UI has only two routes (`/` projects, `/projects/:id` board) and **no global navigation or settings area**.

C1a delivers the first management slice and the navigation foundation the rest of Phase C builds on: a global app shell, a **Manage** area, and three owner-scoped registry screens — **Secrets** (write-only values), **Skills**, and **MCP servers** — each a full create/read/update/delete surface over the existing `capabilities` API.

Per-agent capability **grants** (assigning registry items to agents) need a Teams/Agents management surface that doesn't exist yet; that is a separate slice (**C1b**), explicitly out of scope here.

### C1a success criterion

> From the running app, click **Manage** in the header, land on **Secrets**, create a secret, set its value (the value is never shown back), then switch to **Skills** and **MCP servers** in the sidebar and create/edit/delete entries — all changes persist via the `capabilities` API and survive a reload. The existing notification bell now lives in the global header and is reachable from every screen.

## 2. Scope

### In scope
- A global **`AppLayout`** (header: brand · Projects · Manage · the existing `NotificationBell`) wrapping all routes via `<Outlet/>`.
- A nested **`ManageLayout`** (left sidebar) under `/manage`, plus redirect `/manage` → `/manage/secrets`.
- **Secrets** screen: list (name · description · `has_value` badge · created), create, **set value** (write-only `PUT`), edit metadata, delete.
- **Skills** screen: list (name · description · source), create, edit, delete.
- **MCP servers** screen: list (name · transport · command/URL · tool count), create, edit, delete, with a `tool_allowlist` chip editor.
- A `lib/api/capabilities.ts` data module + per-resource React Query hooks; `Skill`/`McpServer`/`Secret` types in `lib/api/types.ts`.
- Moving the existing `NotificationBell` from `BoardPage` into the global header.
- Vitest + Testing Library + MSW tests per existing convention; `tsc --noEmit` + `npm run build` green.

### Out of scope (later slices)
- **Teams/Agents management + per-agent grants** → C1b (its own spec/plan/PR).
- **Audit viewer, run inspector, model config + budgets, autonomy dial, memory diff review** → later Phase C slices.
- **RAG indexes** (Phase B), **multi-user RBAC** (Phase B).
- **Secret value retrieval/display** — values are write-only by design; the UI never reads or shows them.
- **Skill authoring / `SKILL.md` editing in-app**, MCP live connection testing — registry metadata only here.
- Any **backend change** — the `capabilities` API is already complete; C1a is frontend-only.

## 3. Decisions log

| Decision | Choice | Rationale |
|---|---|---|
| Navigation | **Global `AppLayout` header + nested `ManageLayout` sidebar** | No nav exists; a Manage area with a sidebar scales as Phase C adds Teams/Audit/Budgets/Models screens |
| Component sharing | **Shared chrome (`ManageLayout`, `ResourceTable`, `ConfirmDialog`) + per-screen forms** (Approach A) | KISS: the three forms genuinely differ (write-only secret value, MCP transport + tool-allowlist); a generic config-driven manager would over-abstract (YAGNI) |
| Bell placement | **Move `NotificationBell` into the global header** | It's a global concern; the board is no longer the only screen |
| Secret values | **Write-only; UI never reads a value** | Matches the A5c-3a backend (`has_value` only on reads); the value is set via `PUT /secrets/{id}/value` and immediately cleared from client state |
| Data scope | **Owner-scoped registries (no project context)** | Secrets/skills/MCP belong to the workspace, not a project; the API is already owner-scoped |
| Routing | **`react-router` nested routes + `<Outlet/>`** | Standard pattern; existing app already uses `createBrowserRouter` |
| Backend | **None** | `capabilities` API covers all CRUD + secret value already |

## 4. Architecture (files)

```
ui/src/
  app/
    router.tsx          # MODIFY: wrap routes in <AppLayout>; add nested /manage routes
    AppLayout.tsx       # NEW: global header (brand, nav links, NotificationBell) + <Outlet/>
  features/
    board/
      BoardPage.tsx     # MODIFY: remove the inline NotificationBell (now in AppLayout)
    manage/
      ManageLayout.tsx  # NEW: sidebar nav (Secrets/Skills/MCP) + <Outlet/>
      SecretsPage.tsx   # NEW
      SkillsPage.tsx    # NEW
      McpServersPage.tsx# NEW
      SecretFormDialog.tsx / SetSecretValueDialog.tsx
      SkillFormDialog.tsx
      McpServerFormDialog.tsx
      useSecrets.ts / useSkills.ts / useMcpServers.ts   # React Query hooks (queries + mutations)
      *.test.tsx        # per-screen tests
    components/
      ResourceTable.tsx # NEW: small reusable table (columns + row actions)
      ConfirmDialog.tsx # NEW: reusable confirm-delete
  lib/api/
    capabilities.ts     # NEW: skills/mcpServers/secrets fetch+mutate fns + *Keys factories
    types.ts            # MODIFY: add Skill, McpServer, Secret types
```

Placement follows the existing per-feature convention (`features/<area>/Page.tsx` + `use<Resource>.ts` + `*.test.tsx`, e.g. `features/projects`). Reusable cross-feature bits go in `features/components/` — or wherever the repo already keeps shared UI; match the established home and only introduce `features/components/` if none exists.

## 5. Navigation & routing

`router.tsx` becomes a layout route tree:

- `AppLayout` (element) wraps everything; renders the header and an `<Outlet/>`.
  - `/` → `ProjectsPage`
  - `/projects/:projectId` → `BoardPage`
  - `/manage` → `ManageLayout` (element, renders sidebar + `<Outlet/>`)
    - index → `<Navigate to="secrets" replace />`
    - `secrets` → `SecretsPage`
    - `skills` → `SkillsPage`
    - `mcp-servers` → `McpServersPage`

Header: brand link to `/`, nav links **Projects** (`/`) and **Manage** (`/manage`) with active styling via `NavLink`, and the `NotificationBell` (moved here). Sidebar: `NavLink`s for Secrets / Skills / MCP servers with active styling, laid out per the approved mock (left rail + content).

## 6. Screens

### 6.1 Secrets (`/manage/secrets`)
- **List** (`GET /secrets`): columns name · description · status badge (`● set` when `has_value`, `○ empty` otherwise) · created.
- **New** (`POST /secrets`, body `{name, description}`) — dialog; on success invalidate the list. Creation never sets a value.
- **Set value** (per row, `PUT /secrets/{id}/value`, body `{value}`) — a dialog with a single password input; on submit, send the value, then **clear it from component state immediately**; the value is never echoed or stored client-side. A `503` ("secret encryption key not configured") surfaces as a friendly inline message.
- **Edit** metadata (`PATCH /secrets/{id}`, `{name?, description?}`).
- **Delete** (`DELETE /secrets/{id}`) via `ConfirmDialog`.

### 6.2 Skills (`/manage/skills`)
- **List** (`GET /skills`): name · description · source.
- **New** (`POST /skills`, `{name, description, source}`), **Edit** (`PATCH /skills/{id}`), **Delete** (`DELETE /skills/{id}`).

### 6.3 MCP servers (`/manage/mcp-servers`)
- **List** (`GET /mcp-servers`): name · transport (`stdio`/`http`) · command/URL · tool count (`tool_allowlist.length`).
- **New/Edit** (`POST`/`PATCH /mcp-servers/{id}`, `{name, transport, command_or_url, tool_allowlist}`): a transport `<select>` (stdio|http), a text field for command/URL, and a **tool-allowlist chip editor** (type a tool id like `mcp__server__tool`, Enter to add, ✕ to remove).
- **Delete** (`DELETE /mcp-servers/{id}`) via `ConfirmDialog`.

## 7. Data layer

`lib/api/capabilities.ts` exports, for each resource, a `*Keys` factory and typed functions over the existing client helpers (`apiGetPage`, `apiPost`, `apiPatch`, `apiDelete`, plus a new `apiPut` for the secret-value endpoint, mirroring the existing helpers):

```ts
export const secretKeys = { all: ["secrets"] as const };
export async function listSecrets(): Promise<Secret[]> { /* GET /secrets?page_size=200 */ }
export async function createSecret(input: CreateSecretInput): Promise<Secret>;
export async function updateSecret(id: string, input: UpdateSecretInput): Promise<Secret>;
export async function setSecretValue(id: string, value: string): Promise<Secret>;  // PUT
export async function deleteSecret(id: string): Promise<{ deleted: string }>;
// …same shape for skills (/skills) and mcpServers (/mcp-servers)
```

Types in `types.ts`: `Secret { id; name; description; has_value: boolean; created_at }` (note: **no value field** — reads never include it), `Skill { id; name; description; source; created_at }`, `McpServer { id; name; transport: "stdio" | "http"; command_or_url; tool_allowlist: string[]; created_at }`.

Per-resource hooks (`useSecrets.ts` etc.) follow the `useProjects`/`useCreateProject` pattern: a `useQuery` for the list and `useMutation`s for create/update/set-value/delete that `invalidateQueries` on the list key. `client.ts` gains an `apiPut<T>(path, body)` helper (one-liner mirroring `apiPatch`).

## 8. Error handling

- All calls go through the envelope-aware client; failures throw `ApiError(status, message)`. Dialogs catch and render `error.message` inline; list-level load errors render a friendly retry message (consistent with existing features / `ErrorBoundary`).
- Secret **set-value 503** is handled explicitly with copy pointing at the missing encryption key, not a generic failure.
- Delete is always behind `ConfirmDialog`; mutations disable their submit button while pending.
- No secret value is ever placed in query cache, component state beyond the in-flight submit, logs, or the DOM after submit.

## 9. Testing (Vitest + Testing Library + MSW)

Follow the repo convention (inline `QueryClientProvider` + `MemoryRouter`, per-test `server.use(http.…)`; `onUnhandledRequest: "error"`):

- **AppLayout/routing:** header shows Projects + Manage links and the `NotificationBell`; clicking Manage routes to `/manage/secrets`; sidebar links switch screens.
- **Secrets:** list renders rows with the correct `set`/`empty` badge; create flow posts and refreshes; **set-value** dialog submits and the entered value never appears in the rendered DOM afterward; 503 shows the encryption-key message; delete confirms then removes.
- **Skills / MCP servers:** list render, create, edit, delete; MCP tool-allowlist chip add/remove updates the payload.
- `tsc --noEmit` and `npm run build` succeed.

## 10. Risks

- **Routing refactor touches existing pages** — wrapping `/` and `/projects/:id` in `AppLayout` and moving the bell could disturb `BoardPage`/`ProjectsPage` tests. Mitigation: keep page bodies unchanged; update only the bell mount + add the layout; run the full UI suite.
- **Shared-chrome creep** — `ResourceTable`/`ConfirmDialog` must stay genuinely generic and small; if a screen needs special behavior, keep it in that screen, not the shared component.
- **Secret value leakage** — covered by an explicit test asserting the submitted value is absent from the DOM and never cached; reviewers should treat this as security-sensitive.

## 11. Cross-references

- **C1b** (next slice): Teams/Agents management + the per-agent grant editor that assigns these registry items (`skill_ids`/`mcp_server_ids`/`secret_ids`/`allowed_tools`) to agents via the existing `agents` API.
- Later Phase C slices (audit viewer, run inspector, model config + budgets, autonomy dial, memory diff review) reuse the `AppLayout` + `ManageLayout` shell introduced here.
