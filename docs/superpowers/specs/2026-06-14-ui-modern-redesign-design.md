# UI Modern Redesign — Design Spec

**Date:** 2026-06-14
**Status:** Approved (brainstorming)
**Branch:** `feat/ui-modern-redesign`

## Problem

The `ui/` board app is functional but visually plain: default Tailwind grays
and blues, flat cards, no design-token system, no dark mode, system fonts, and
minimal hierarchy. yaah is a tool people stare at for long stretches (kanban of
projects → epics → features → tasks, runs, PRs, chat), so it should look like a
serious modern dev tool.

## Goals

- A cohesive **modern dev-tool aesthetic** (Linear/Vercel family): clean, dense,
  high-contrast, neutral surfaces with one accent, crisp typography.
- **Dark-first** theme with a light theme, both driven by one set of components.
- A reusable **design-token + primitive layer** so future features stay
  consistent without re-inventing styles.
- Restyle **every existing surface** — no half-migrated UI.

## Non-Goals

- No new runtime UI dependency (no shadcn/ui, MUI, Mantine).
- No behavior/logic changes — this is purely presentational + theming.
- No new features or routes.
- No unrelated refactoring beyond what restyling touches.

## Approach

A three-layer migration, shipped as **one PR**:

1. **Token layer** — CSS variables (light + dark) in `index.css`, wired into
   `tailwind.config.ts` so semantic utilities work everywhere.
2. **Primitive layer** — small in-repo components in `src/ui/`, dependency-free.
3. **Surface layer** — restyle every feature component onto tokens + primitives.

Rejected alternatives: **shadcn/ui** (pulls in CLI/Radix/cva conventions, larger
departure from the lean setup) and **full library MUI/Mantine** (heavy runtime
dep, opinionated styling that fights Tailwind).

## Design Tokens & Theming

**Semantic color tokens**, defined under `:root` and `.dark`, exposed to Tailwind
via the `rgb(var(--token) / <alpha-value>)` pattern so opacity utilities work:

- Surfaces: `--bg` (app), `--bg-subtle` (columns/sidebar), `--surface`
  (cards/dialogs), `--surface-hover`
- Lines: `--border`, `--border-strong`
- Text: `--text`, `--text-muted`, `--text-subtle`
- Accent: `--accent`, `--accent-fg`, `--accent-subtle` — **blue-violet** hue
- Status: `--success`, `--warning`, `--danger`, `--info`, each with a `-subtle`
  background variant (drives `RunStatusBadge` and blocked/failed badges)
- `--radius` scale + subtle elevation shadow tokens

**Tailwind config:** add `darkMode: 'class'`; map tokens into
`theme.extend.colors` (e.g. `colors.surface`, `colors.muted`, `colors.accent`),
`borderRadius`, and `boxShadow`. Set Inter as the default `fontFamily.sans`.

**Theme switching:** a `useTheme` hook persists choice in `localStorage`
(default **dark**) and toggles the `.dark` class on `<html>`. A toggle button
sits in the header next to the notification bell. A tiny inline script in
`index.html` applies the stored class before first paint to avoid a flash.

**Typography:** adopt **Inter** via `@fontsource-variable/inter` (build-time,
bundled — a dev dependency, not a runtime UI library), set as the default sans
font with tightened letter-spacing on headings.

## Primitives (`src/ui/`)

Each is small, typed, variant-driven, and unit-tested. A dependency-free `cn()`
class-merge helper supports them.

- **Button** — `primary | secondary | ghost | danger`, `sm | md`, loading state
- **Card / Surface** — elevated container using border + shadow tokens
- **Badge** — status-colored; backs run status + blocked/failed indicators
- **Input / Textarea / Select / Field** — labeled form controls
- **Dialog** — focus-trapped modal shell backing the three existing dialogs
- **IconButton**, **Spinner**, **EmptyState**

Each primitive answers: what it does (one visual concern), how to use it (typed
props + variants), what it depends on (only tokens + `cn`). Consumers never read
internals; internals can change without breaking consumers.

## Surfaces to Restyle (all)

- **App shell:** `AppLayout` (sticky header, refined nav, theme toggle),
  `ManageLayout` (sidebar active-state pills), `NotificationBell`
- **Board:** `Board`, `Column` (subtle surface, count chip), `TaskCard`
  (elevation, drag affordance, status badge)
- **Projects:** `ProjectsPage` (card grid vs. plain list), `CreateProjectDialog`
- **Manage:** `SecretsPage`, `SkillsPage`, `McpServersPage`,
  `SetSecretValueDialog`, `ResourceTable` (hover rows, refined header)
- **Runs:** `RunSection`, `RunActions`, `RunStatusBadge`, `MemoryProposalCard`
- **Chat:** `ChatRail`
- **Work items:** `BoardPage`, `HierarchyTree`, `AcceptanceCriteria`
- **Shared:** `ConfirmDialog`; loading/error/empty states standardized via
  `Spinner` / `EmptyState`

## Error / Edge Handling

- Loading, error, and empty states get consistent primitive-based treatments
  (`Spinner`, inline `--danger` text, `EmptyState`) instead of ad-hoc strings.
- Theme toggle degrades gracefully if `localStorage` is unavailable (falls back
  to dark default, no throw).

## Testing

- New unit tests per primitive: variants render with expected roles/labels;
  `Dialog` traps focus and closes on escape/overlay; `useTheme` toggles the
  `.dark` class and persists.
- Existing behavior tests must stay green — they assert roles/text, not classes;
  restyling must preserve accessible names and semantics.
- Verify via `pnpm test` (vitest) + `pnpm lint` (tsc) and a manual dark/light
  pass across surfaces. Keep the 80% coverage gate.

## Rollout

**Single PR** off `feat/ui-modern-redesign`: token system + theming + primitives
first, then all surfaces migrated, then tests. Reviewed PR into `main` per the
project worktree → PR workflow.
