# UI Modern Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the `ui/` board app a cohesive modern dev-tool look (Linear/Vercel family) with a dark-first + light theme, built on a reusable design-token + primitive layer, restyling every existing surface.

**Architecture:** Three layers — (1) CSS-variable design tokens wired into Tailwind, (2) a small set of dependency-free in-repo primitives in `src/ui/`, (3) every feature surface restyled onto those tokens + primitives. Theme switching toggles a `.dark` class on `<html>`, persisted in `localStorage`, default dark, with a no-flash inline script.

**Tech Stack:** React 18, Vite, Tailwind 3.4 (`darkMode: 'class'`), TypeScript, Vitest + Testing Library, `@fontsource-variable/inter` (build-time font, no runtime UI library).

**Spec:** `docs/superpowers/specs/2026-06-14-ui-modern-redesign-design.md`

**Working directory:** worktree `../yaah-ui-redesign`, branch `feat/ui-modern-redesign`. All UI paths below are relative to `ui/`. Run all `pnpm` commands from `ui/`.

---

## Token Naming Reference (used throughout)

Tailwind color keys map to CSS variables via `rgb(var(--token) / <alpha-value>)`:

| Tailwind utility | CSS var | Role |
|---|---|---|
| `bg-canvas` | `--canvas` | app background |
| `bg-panel` | `--panel` | columns, sidebars, sunken areas |
| `bg-surface` / `bg-surface-hover` | `--surface` / `--surface-hover` | cards, dialogs, rows |
| `text-fg` | `--fg` | primary text |
| `text-muted` | `--muted` | secondary text |
| `text-subtle` | `--subtle` | tertiary / placeholder |
| `border-line` / `border-line-strong` | `--line` / `--line-strong` | borders |
| `bg-accent` / `text-accent` / `text-accent-fg` / `bg-accent-subtle` | `--accent*` | accent (blue-violet) |
| `bg-success(-subtle)`, `text-success` … and `warning`/`danger`/`info` | status tokens | badges, status |

**Migration cheatsheet** (applied during surface tasks):
- `bg-white` → `bg-surface`; `bg-gray-50` (container) → `bg-panel`; `bg-gray-100/50` (hover) → `hover:bg-surface-hover`; `bg-gray-100` (chip) → `bg-surface-hover`
- bare `border` (color) → `border border-line`
- `text-gray-900` → `text-fg`; `text-gray-700`/`-600` → `text-muted`; `text-gray-500`/`-400` → `text-subtle`
- primary button `bg-blue-600 text-white …` → `<Button>`; secondary `border …` button → `<Button variant="secondary">`
- inline link `text-blue-700` → `text-accent hover:underline`
- ad-hoc modal (`fixed inset-0 … bg-black/30`) → `<Dialog>`
- status color maps → `<Badge tone="…">` or status tokens

---

## Phase 1 — Foundation (tokens, theming, primitives)

### Task 1: Design tokens in `index.css`

**Files:**
- Modify: `src/index.css`

- [ ] **Step 1: Replace `src/index.css` with tokens + base body styles**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --canvas: 255 255 255;
  --panel: 248 249 251;
  --surface: 255 255 255;
  --surface-hover: 244 245 247;
  --fg: 17 24 39;
  --muted: 75 85 99;
  --subtle: 156 163 175;
  --line: 229 231 235;
  --line-strong: 209 213 219;
  --accent: 79 70 229;
  --accent-fg: 255 255 255;
  --accent-subtle: 238 242 255;
  --success: 22 163 74;
  --success-subtle: 220 252 231;
  --warning: 180 83 9;
  --warning-subtle: 254 243 199;
  --danger: 220 38 38;
  --danger-subtle: 254 226 226;
  --info: 37 99 235;
  --info-subtle: 219 234 254;
}

.dark {
  --canvas: 9 9 11;
  --panel: 24 24 27;
  --surface: 24 24 27;
  --surface-hover: 39 39 42;
  --fg: 244 244 245;
  --muted: 161 161 170;
  --subtle: 113 113 122;
  --line: 39 39 42;
  --line-strong: 63 63 70;
  --accent: 129 140 248;
  --accent-fg: 9 9 11;
  --accent-subtle: 30 27 75;
  --success: 74 222 128;
  --success-subtle: 20 51 33;
  --warning: 250 204 21;
  --warning-subtle: 55 42 10;
  --danger: 248 113 113;
  --danger-subtle: 60 24 24;
  --info: 96 165 250;
  --info-subtle: 23 37 64;
}

body {
  @apply bg-canvas text-fg antialiased;
}
```

- [ ] **Step 2: Commit**

```bash
git add ui/src/index.css
git commit -m "feat(ui): add design-token CSS variables (light + dark)"
```

### Task 2: Wire tokens + Inter font into Tailwind

**Files:**
- Modify: `tailwind.config.ts`
- Modify: `package.json` (add `@fontsource-variable/inter` devDependency)
- Modify: `src/main.tsx` (import the font)

- [ ] **Step 1: Install the font package**

Run: `pnpm add -D @fontsource-variable/inter`
Expected: package added to `devDependencies`, lockfile updated.

- [ ] **Step 2: Replace `tailwind.config.ts`**

```ts
import type { Config } from "tailwindcss";

const token = (name: string) => `rgb(var(${name}) / <alpha-value>)`;

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: token("--canvas"),
        panel: token("--panel"),
        surface: { DEFAULT: token("--surface"), hover: token("--surface-hover") },
        fg: token("--fg"),
        muted: token("--muted"),
        subtle: token("--subtle"),
        line: { DEFAULT: token("--line"), strong: token("--line-strong") },
        accent: { DEFAULT: token("--accent"), fg: token("--accent-fg"), subtle: token("--accent-subtle") },
        success: { DEFAULT: token("--success"), subtle: token("--success-subtle") },
        warning: { DEFAULT: token("--warning"), subtle: token("--warning-subtle") },
        danger: { DEFAULT: token("--danger"), subtle: token("--danger-subtle") },
        info: { DEFAULT: token("--info"), subtle: token("--info-subtle") },
      },
      fontFamily: {
        sans: ["InterVariable", "Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
} satisfies Config;
```

- [ ] **Step 3: Import the font in `src/main.tsx`**

Add this import at the very top of `src/main.tsx`, above the existing imports:

```ts
import "@fontsource-variable/inter";
```

- [ ] **Step 4: Verify the build compiles**

Run: `pnpm lint`
Expected: PASS (tsc no-emit, no type errors).

- [ ] **Step 5: Commit**

```bash
git add ui/tailwind.config.ts ui/package.json ui/pnpm-lock.yaml ui/src/main.tsx
git commit -m "feat(ui): map design tokens into Tailwind and load Inter"
```

### Task 3: No-flash theme bootstrap in `index.html`

**Files:**
- Modify: `index.html`

- [ ] **Step 1: Add the pre-paint theme script to `<head>`**

Insert this `<script>` inside `<head>`, after the `<title>` line:

```html
<script>
  try {
    var t = localStorage.getItem("yaah-theme");
    if (t !== "light") document.documentElement.classList.add("dark");
  } catch (e) {}
</script>
```

- [ ] **Step 2: Commit**

```bash
git add ui/index.html
git commit -m "feat(ui): apply stored theme before first paint (no flash)"
```

### Task 4: `cn()` class-merge helper

**Files:**
- Create: `src/ui/cn.ts`
- Test: `src/ui/cn.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { cn } from "./cn";

test("joins truthy class names and drops falsy ones", () => {
  expect(cn("a", false, null, undefined, "b")).toBe("a b");
});

test("returns empty string when nothing truthy", () => {
  expect(cn(false, null, undefined)).toBe("");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- src/ui/cn.test.ts`
Expected: FAIL — cannot resolve `./cn`.

- [ ] **Step 3: Implement `src/ui/cn.ts`**

```ts
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- src/ui/cn.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/ui/cn.ts ui/src/ui/cn.test.ts
git commit -m "feat(ui): add cn class-merge helper"
```

### Task 5: `useTheme` hook

**Files:**
- Create: `src/features/theme/useTheme.ts`
- Test: `src/features/theme/useTheme.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { act, renderHook } from "@testing-library/react";
import { useTheme } from "./useTheme";

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
});

test("defaults to dark and applies the dark class", () => {
  const { result } = renderHook(() => useTheme());
  expect(result.current.theme).toBe("dark");
  expect(document.documentElement.classList.contains("dark")).toBe(true);
});

test("toggle switches to light, removes class, and persists", () => {
  const { result } = renderHook(() => useTheme());
  act(() => result.current.toggle());
  expect(result.current.theme).toBe("light");
  expect(document.documentElement.classList.contains("dark")).toBe(false);
  expect(localStorage.getItem("yaah-theme")).toBe("light");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- src/features/theme/useTheme.test.ts`
Expected: FAIL — cannot resolve `./useTheme`.

- [ ] **Step 3: Implement `src/features/theme/useTheme.ts`**

```ts
import { useEffect, useState } from "react";

export type Theme = "light" | "dark";
const STORAGE_KEY = "yaah-theme";

function readStored(): Theme {
  try {
    return localStorage.getItem(STORAGE_KEY) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(readStored);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* ignore unavailable storage */
    }
  }, [theme]);

  const toggle = () => setTheme((t) => (t === "dark" ? "light" : "dark"));
  return { theme, toggle };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- src/features/theme/useTheme.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/features/theme/useTheme.ts ui/src/features/theme/useTheme.test.ts
git commit -m "feat(ui): add useTheme hook (dark-first, persisted)"
```

### Task 6: `ThemeToggle` component

**Files:**
- Create: `src/features/theme/ThemeToggle.tsx`
- Test: `src/features/theme/ThemeToggle.test.tsx`
- Depends on: Task 5, Task 13 (`IconButton`)

> Note: this task uses `IconButton` from Task 13. If executing strictly in order, do Task 13 before Task 6, or temporarily use a plain `<button>` and swap to `IconButton` when Task 13 lands. The code below assumes `IconButton` exists.

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeToggle } from "./ThemeToggle";

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
});

test("toggles theme on click and exposes an accessible label", async () => {
  render(<ThemeToggle />);
  // starts dark -> label offers switching to light
  const button = screen.getByRole("button", { name: /switch to light theme/i });
  await userEvent.click(button);
  expect(screen.getByRole("button", { name: /switch to dark theme/i })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- src/features/theme/ThemeToggle.test.tsx`
Expected: FAIL — cannot resolve `./ThemeToggle`.

- [ ] **Step 3: Implement `src/features/theme/ThemeToggle.tsx`**

```tsx
import { IconButton } from "../../ui/IconButton";
import { useTheme } from "./useTheme";

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const toLight = theme === "dark";
  return (
    <IconButton label={toLight ? "Switch to light theme" : "Switch to dark theme"} onClick={toggle}>
      <span aria-hidden="true">{toLight ? "☀️" : "🌙"}</span>
    </IconButton>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- src/features/theme/ThemeToggle.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/features/theme/ThemeToggle.tsx ui/src/features/theme/ThemeToggle.test.tsx
git commit -m "feat(ui): add ThemeToggle"
```

### Task 7: `Spinner` primitive

**Files:**
- Create: `src/ui/Spinner.tsx`
- Test: `src/ui/Spinner.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { Spinner } from "./Spinner";

test("renders an accessible loading status", () => {
  render(<Spinner />);
  expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- src/ui/Spinner.test.tsx`
Expected: FAIL — cannot resolve `./Spinner`.

- [ ] **Step 3: Implement `src/ui/Spinner.tsx`**

```tsx
import { cn } from "./cn";

export function Spinner({ size = "md", className }: { size?: "sm" | "md"; className?: string }) {
  const dim = size === "sm" ? "h-4 w-4" : "h-5 w-5";
  return (
    <svg
      className={cn("animate-spin text-current", dim, className)}
      viewBox="0 0 24 24"
      fill="none"
      role="status"
      aria-label="Loading"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8v4a4 4 0 0 0-4 4H4z" />
    </svg>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- src/ui/Spinner.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/ui/Spinner.tsx ui/src/ui/Spinner.test.tsx
git commit -m "feat(ui): add Spinner primitive"
```

### Task 8: `Button` primitive

**Files:**
- Create: `src/ui/Button.tsx`
- Test: `src/ui/Button.test.tsx`
- Depends on: Task 7 (`Spinner`)

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { Button } from "./Button";

test("renders children and forwards type", () => {
  render(<Button type="submit">Save</Button>);
  const btn = screen.getByRole("button", { name: "Save" });
  expect(btn).toHaveAttribute("type", "submit");
});

test("is disabled and shows a spinner when loading", () => {
  render(<Button loading>Save</Button>);
  expect(screen.getByRole("button", { name: /save/i })).toBeDisabled();
  expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- src/ui/Button.test.tsx`
Expected: FAIL — cannot resolve `./Button`.

- [ ] **Step 3: Implement `src/ui/Button.tsx`**

```tsx
import type { ButtonHTMLAttributes } from "react";
import { cn } from "./cn";
import { Spinner } from "./Spinner";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-canvas disabled:opacity-50 disabled:pointer-events-none";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-accent-fg hover:bg-accent/90",
  secondary: "border border-line bg-surface text-fg hover:bg-surface-hover",
  ghost: "text-muted hover:bg-surface-hover hover:text-fg",
  danger: "bg-danger text-white hover:bg-danger/90",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-sm",
  md: "h-9 px-4 text-sm",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

export function Button({ variant = "primary", size = "md", loading, className, children, disabled, ...rest }: ButtonProps) {
  return (
    <button className={cn(BASE, VARIANTS[variant], SIZES[size], className)} disabled={disabled || loading} {...rest}>
      {loading && <Spinner size="sm" />}
      {children}
    </button>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- src/ui/Button.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/ui/Button.tsx ui/src/ui/Button.test.tsx
git commit -m "feat(ui): add Button primitive"
```

### Task 9: `Badge` primitive

**Files:**
- Create: `src/ui/Badge.tsx`
- Test: `src/ui/Badge.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { Badge } from "./Badge";

test("renders its label with the tone classes", () => {
  render(<Badge tone="danger">failed</Badge>);
  const badge = screen.getByText("failed");
  expect(badge.className).toContain("text-danger");
  expect(badge.className).toContain("bg-danger-subtle");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- src/ui/Badge.test.tsx`
Expected: FAIL — cannot resolve `./Badge`.

- [ ] **Step 3: Implement `src/ui/Badge.tsx`**

```tsx
import type { ReactNode } from "react";
import { cn } from "./cn";

export type BadgeTone = "neutral" | "success" | "warning" | "danger" | "info" | "accent";

const TONES: Record<BadgeTone, string> = {
  neutral: "bg-surface-hover text-muted",
  success: "bg-success-subtle text-success",
  warning: "bg-warning-subtle text-warning",
  danger: "bg-danger-subtle text-danger",
  info: "bg-info-subtle text-info",
  accent: "bg-accent-subtle text-accent",
};

export function Badge({ tone = "neutral", className, children }: { tone?: BadgeTone; className?: string; children: ReactNode }) {
  return (
    <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium", TONES[tone], className)}>
      {children}
    </span>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- src/ui/Badge.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/ui/Badge.tsx ui/src/ui/Badge.test.tsx
git commit -m "feat(ui): add Badge primitive"
```

### Task 10: `Card` primitive

**Files:**
- Create: `src/ui/Card.tsx`
- Test: `src/ui/Card.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { Card } from "./Card";

test("renders children inside a surface container", () => {
  render(<Card>contents</Card>);
  const el = screen.getByText("contents");
  expect(el.className).toContain("bg-surface");
  expect(el.className).toContain("border-line");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- src/ui/Card.test.tsx`
Expected: FAIL — cannot resolve `./Card`.

- [ ] **Step 3: Implement `src/ui/Card.tsx`**

```tsx
import type { HTMLAttributes } from "react";
import { cn } from "./cn";

export function Card({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-lg border border-line bg-surface shadow-sm", className)} {...rest} />;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- src/ui/Card.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/ui/Card.tsx ui/src/ui/Card.test.tsx
git commit -m "feat(ui): add Card primitive"
```

### Task 11: Form primitives — `Input`, `Textarea`, `Select`, `Field`

**Files:**
- Create: `src/ui/Field.tsx` (exports `Input`, `Textarea`, `Select`, `Field`)
- Test: `src/ui/Field.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { Field, Input } from "./Field";

test("associates a label with its control", () => {
  render(
    <Field label="Name">
      <Input value="" onChange={() => {}} />
    </Field>,
  );
  expect(screen.getByText("Name")).toBeInTheDocument();
  expect(screen.getByRole("textbox")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- src/ui/Field.test.tsx`
Expected: FAIL — cannot resolve `./Field`.

- [ ] **Step 3: Implement `src/ui/Field.tsx`**

```tsx
import { forwardRef, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { cn } from "./cn";

const CONTROL =
  "w-full rounded-md border border-line bg-surface px-3 py-2 text-sm text-fg placeholder:text-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...rest }, ref) => <input ref={ref} className={cn(CONTROL, className)} {...rest} />,
);
Input.displayName = "Input";

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...rest }, ref) => <textarea ref={ref} className={cn(CONTROL, className)} {...rest} />,
);
Textarea.displayName = "Textarea";

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, ...rest }, ref) => <select ref={ref} className={cn(CONTROL, className)} {...rest} />,
);
Select.displayName = "Select";

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium text-fg">{label}</span>
      {children}
    </label>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- src/ui/Field.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/ui/Field.tsx ui/src/ui/Field.test.tsx
git commit -m "feat(ui): add Input/Textarea/Select/Field primitives"
```

### Task 12: `Dialog` primitive (focus + escape + overlay)

**Files:**
- Create: `src/ui/Dialog.tsx`
- Test: `src/ui/Dialog.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Dialog } from "./Dialog";

test("Escape and overlay click close; inside click does not", async () => {
  const onClose = vi.fn();
  render(
    <Dialog title="Edit" onClose={onClose}>
      <button>Inside</button>
    </Dialog>,
  );
  const dialog = screen.getByRole("dialog", { name: "Edit" });
  await userEvent.click(screen.getByRole("button", { name: "Inside" }));
  expect(onClose).not.toHaveBeenCalled();
  await userEvent.keyboard("{Escape}");
  expect(onClose).toHaveBeenCalledTimes(1);
  expect(dialog).toHaveAttribute("aria-modal", "true");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- src/ui/Dialog.test.tsx`
Expected: FAIL — cannot resolve `./Dialog`.

- [ ] **Step 3: Implement `src/ui/Dialog.tsx`**

```tsx
import { useEffect, useRef, type ReactNode } from "react";

export function Dialog({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key !== "Tab" || !panelRef.current) return;
      const focusables = panelRef.current.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previouslyFocused?.focus();
    };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" onClick={onClose}>
      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="w-full max-w-md rounded-lg border border-line bg-surface p-5 shadow-lg focus-visible:outline-none"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-4 text-lg font-semibold text-fg">{title}</h2>
        {children}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- src/ui/Dialog.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/ui/Dialog.tsx ui/src/ui/Dialog.test.tsx
git commit -m "feat(ui): add Dialog primitive (focus trap, escape, overlay)"
```

### Task 13: `IconButton` + `EmptyState` primitives

**Files:**
- Create: `src/ui/IconButton.tsx`
- Create: `src/ui/EmptyState.tsx`
- Test: `src/ui/IconButton.test.tsx`
- Test: `src/ui/EmptyState.test.tsx`

- [ ] **Step 1: Write the failing tests**

`src/ui/IconButton.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { IconButton } from "./IconButton";

test("exposes its label as the accessible name", () => {
  render(<IconButton label="Notifications"><span aria-hidden>🔔</span></IconButton>);
  expect(screen.getByRole("button", { name: "Notifications" })).toBeInTheDocument();
});
```

`src/ui/EmptyState.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { EmptyState } from "./EmptyState";

test("renders title and description", () => {
  render(<EmptyState title="No projects" description="Create one to start." />);
  expect(screen.getByText("No projects")).toBeInTheDocument();
  expect(screen.getByText("Create one to start.")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pnpm test -- src/ui/IconButton.test.tsx src/ui/EmptyState.test.tsx`
Expected: FAIL — modules not found.

- [ ] **Step 3: Implement both primitives**

`src/ui/IconButton.tsx`:

```tsx
import type { ButtonHTMLAttributes } from "react";
import { cn } from "./cn";

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string;
}

export function IconButton({ label, className, children, ...rest }: IconButtonProps) {
  return (
    <button
      type="button"
      aria-label={label}
      className={cn(
        "inline-flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface-hover hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}
```

`src/ui/EmptyState.tsx`:

```tsx
import type { ReactNode } from "react";

export function EmptyState({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-line py-12 text-center">
      <p className="text-sm font-medium text-fg">{title}</p>
      {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pnpm test -- src/ui/IconButton.test.tsx src/ui/EmptyState.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/ui/IconButton.tsx ui/src/ui/EmptyState.tsx ui/src/ui/IconButton.test.tsx ui/src/ui/EmptyState.test.tsx
git commit -m "feat(ui): add IconButton and EmptyState primitives"
```

---

## Phase 2 — Surface restyle

> Surface tasks are presentational. Each preserves existing behavior, roles, and accessible names, so existing tests must stay green. Where a task references a primitive, import it from `../../ui/<Name>` (adjust depth to the file's location).

### Task 14: App shell — `AppLayout` with theme toggle

**Files:**
- Modify: `src/app/AppLayout.tsx`
- Check: `src/app/AppLayout.test.tsx` (must stay green)

- [ ] **Step 1: Replace `src/app/AppLayout.tsx`**

```tsx
import { NavLink, Outlet } from "react-router-dom";
import { NotificationBell } from "../features/notifications/NotificationBell";
import { ThemeToggle } from "../features/theme/ThemeToggle";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `text-sm transition-colors ${isActive ? "font-semibold text-accent" : "text-muted hover:text-fg"}`;

export function AppLayout() {
  return (
    <div className="flex h-screen flex-col bg-canvas text-fg">
      <header className="flex items-center gap-4 border-b border-line bg-surface/80 px-4 py-2 backdrop-blur">
        <NavLink to="/" className="text-sm font-bold tracking-tight">yaah</NavLink>
        <nav className="flex gap-4">
          <NavLink to="/" end className={linkClass}>Projects</NavLink>
          <NavLink to="/manage" className={linkClass}>Manage</NavLink>
        </nav>
        <div className="ml-auto flex items-center gap-1">
          <ThemeToggle />
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

- [ ] **Step 2: Run tests**

Run: `pnpm test -- src/app/AppLayout.test.tsx`
Expected: PASS (nav links + outlet unchanged).

- [ ] **Step 3: Commit**

```bash
git add ui/src/app/AppLayout.tsx
git commit -m "feat(ui): restyle app shell with theme toggle"
```

### Task 15: `NotificationBell`

**Files:**
- Modify: `src/features/notifications/NotificationBell.tsx`
- Check: `src/features/notifications/NotificationBell.test.tsx`

- [ ] **Step 1: Replace `src/features/notifications/NotificationBell.tsx`**

```tsx
import { useState } from "react";
import { Link } from "react-router-dom";
import type { Notification } from "../../lib/api/notifications";
import { IconButton } from "../../ui/IconButton";
import { useNotifications, useUnreadCount } from "./useNotifications";

function NotificationItem({ notification }: { notification: Notification }) {
  const { category, title, action } = notification;
  const label = (
    <div className="flex flex-col">
      <span className="text-[10px] font-semibold uppercase tracking-wide text-subtle">{category}</span>
      <span className="text-sm text-fg">{title}</span>
    </div>
  );

  if (action?.kind === "gate_approval") {
    return (
      <li>
        <Link to={`/runs/${action.run_id}`} className="block px-3 py-2 hover:bg-surface-hover">
          {label}
        </Link>
      </li>
    );
  }

  return <li className="px-3 py-2">{label}</li>;
}

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const { data: count = 0 } = useUnreadCount();
  const { data: notifications = [], isLoading } = useNotifications(open);

  return (
    <div className="relative">
      <IconButton
        label={`${count} unread notifications`}
        aria-expanded={open}
        className="relative"
        onClick={() => setOpen((v) => !v)}
      >
        <span aria-hidden="true">🔔</span>
        {count > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-semibold text-white">
            {count}
          </span>
        )}
      </IconButton>
      {open && (
        <div className="absolute right-0 z-10 mt-2 w-72 overflow-hidden rounded-lg border border-line bg-surface shadow-lg">
          <div className="border-b border-line px-3 py-2 text-xs font-semibold uppercase tracking-wide text-subtle">
            Notifications
          </div>
          {isLoading && <p className="px-3 py-2 text-sm text-subtle">Loading…</p>}
          {!isLoading && notifications.length === 0 && (
            <p className="px-3 py-2 text-sm text-subtle">No notifications.</p>
          )}
          <ul className="max-h-80 divide-y divide-line overflow-auto">
            {notifications.map((n) => (
              <NotificationItem key={n.id} notification={n} />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Run tests**

Run: `pnpm test -- src/features/notifications/NotificationBell.test.tsx`
Expected: PASS (button accessible name `N unread notifications` preserved).

- [ ] **Step 3: Commit**

```bash
git add ui/src/features/notifications/NotificationBell.tsx
git commit -m "feat(ui): restyle notification bell"
```

### Task 16: `ManageLayout` sidebar

**Files:**
- Modify: `src/features/manage/ManageLayout.tsx`

- [ ] **Step 1: Update the link class and chrome in `src/features/manage/ManageLayout.tsx`**

Replace the `linkClass` constant and the two JSX wrapper elements:

```tsx
const linkClass = ({ isActive }: { isActive: boolean }) =>
  `block rounded-md px-3 py-2 text-sm transition-colors ${
    isActive ? "bg-accent-subtle font-medium text-accent" : "text-muted hover:bg-surface-hover hover:text-fg"
  }`;
```

```tsx
    <div className="flex h-full bg-canvas">
      <aside className="w-48 shrink-0 border-r border-line bg-panel p-3">
```

(Leave the `<nav>`, `items` map, and `<section className="flex-1 overflow-auto p-6">` structure unchanged.)

- [ ] **Step 2: Run the manage tests**

Run: `pnpm test -- src/features/manage`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add ui/src/features/manage/ManageLayout.tsx
git commit -m "feat(ui): restyle manage sidebar"
```

### Task 17: Board — `Board`, `Column`, `TaskCard`

**Files:**
- Modify: `src/features/board/Board.tsx`
- Modify: `src/features/board/Column.tsx`
- Modify: `src/features/board/TaskCard.tsx`
- Check: `src/features/board/Board.test.tsx`

- [ ] **Step 1: Update loading/error/empty + container classes in `Board.tsx`**

Replace the three render lines and the column wrapper:

```tsx
  if (isLoading) return <p className="p-4 text-sm text-subtle">Loading board…</p>;
  if (isError) return <p className="p-4 text-sm text-danger">{(error as Error).message}</p>;
```

```tsx
      <div className="flex gap-3 overflow-x-auto p-4">
```

```tsx
      {setStatus.isError && (
        <p className="px-4 text-sm text-danger">Move rejected: {(setStatus.error as Error).message}</p>
      )}
```

(Keep all `DndContext`/grouping logic unchanged.)

- [ ] **Step 2: Replace `Column.tsx` (token surfaces + a count chip)**

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
      className={`flex w-60 shrink-0 flex-col rounded-lg border border-line bg-panel p-2 transition-shadow ${
        isOver ? "ring-2 ring-accent" : ""
      }`}
    >
      <div className="mb-2 flex items-center justify-between px-1">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-subtle">{column.title}</h2>
        <span className="rounded-full bg-surface-hover px-1.5 text-xs text-muted">{items.length}</span>
      </div>
      {items.map((item) => (
        <TaskCard key={item.id} item={item} onOpen={onOpen} />
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Replace `TaskCard.tsx` (elevation + Badge)**

```tsx
import { useDraggable } from "@dnd-kit/core";
import type { WorkItem } from "../../lib/api/types";
import { Badge } from "../../ui/Badge";

const ATTENTION_STATUSES = new Set(["blocked", "failed"]);

export function TaskCard({ item, onOpen }: { item: WorkItem; onOpen: (id: string) => void }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: item.id });
  const style = transform ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` } : undefined;
  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`mb-2 cursor-grab rounded-md border border-line bg-surface p-2.5 text-sm shadow-sm transition-shadow hover:shadow-md active:cursor-grabbing ${
        isDragging ? "opacity-50" : ""
      }`}
      {...listeners}
      {...attributes}
    >
      <button className="text-left font-medium text-fg" onClick={() => onOpen(item.id)}>
        {item.title}
      </button>
      {ATTENTION_STATUSES.has(item.status) && (
        <Badge tone="danger" className="ml-2">
          {item.status}
        </Badge>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run board tests**

Run: `pnpm test -- src/features/board`
Expected: PASS (column titles, card titles, attention badge text unchanged).

- [ ] **Step 5: Commit**

```bash
git add ui/src/features/board/Board.tsx ui/src/features/board/Column.tsx ui/src/features/board/TaskCard.tsx
git commit -m "feat(ui): restyle board, columns, and task cards"
```

### Task 18: `ProjectsPage` (card grid) + `CreateProjectDialog` (onto Dialog)

**Files:**
- Modify: `src/features/projects/ProjectsPage.tsx`
- Modify: `src/features/projects/CreateProjectDialog.tsx`
- Check: `src/features/projects/ProjectsPage.test.tsx`

- [ ] **Step 1: Replace `ProjectsPage.tsx`**

```tsx
import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "../../ui/Button";
import { Card } from "../../ui/Card";
import { EmptyState } from "../../ui/EmptyState";
import { useProjects } from "./useProjects";
import { CreateProjectDialog } from "./CreateProjectDialog";

export default function ProjectsPage() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const { data, isLoading, isError, error } = useProjects();

  return (
    <div className="mx-auto max-w-5xl p-6">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight text-fg">Projects</h1>
        <Button size="sm" onClick={() => setDialogOpen(true)}>New project</Button>
      </div>
      {isLoading && <p className="text-sm text-subtle">Loading…</p>}
      {isError && <p className="text-sm text-danger">{(error as Error).message}</p>}
      {data && data.length === 0 && (
        <EmptyState
          title="No projects yet"
          description="Create your first project to spin up a board."
          action={<Button size="sm" onClick={() => setDialogOpen(true)}>New project</Button>}
        />
      )}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {data?.map((p) => (
          <Card key={p.id} className="p-4 transition-colors hover:bg-surface-hover">
            <Link to={`/projects/${p.id}`} className="font-medium text-fg hover:text-accent">
              {p.name}
            </Link>
          </Card>
        ))}
      </div>
      {dialogOpen && <CreateProjectDialog onClose={() => setDialogOpen(false)} />}
    </div>
  );
}
```

- [ ] **Step 2: Replace `CreateProjectDialog.tsx` (use Dialog + Field/Input/Button)**

```tsx
import { useState } from "react";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { Field, Input } from "../../ui/Field";
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
    <Dialog title="New project" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Repo URL"><Input value={repoUrl} onChange={(e) => setRepoUrl(e.target.value)} /></Field>
        <Field label="Local path"><Input value={localPath} onChange={(e) => setLocalPath(e.target.value)} /></Field>
        {!canSubmit && <p className="text-xs text-subtle">Name and a repo URL or local path are required.</p>}
        {create.isError && <p className="text-xs text-danger">{(create.error as Error).message}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button type="submit" size="sm" disabled={!canSubmit} loading={create.isPending}>Create</Button>
        </div>
      </form>
    </Dialog>
  );
}
```

- [ ] **Step 3: Run project tests**

Run: `pnpm test -- src/features/projects`
Expected: PASS (project links, New project button, field labels, Create button preserved).

- [ ] **Step 4: Commit**

```bash
git add ui/src/features/projects/ProjectsPage.tsx ui/src/features/projects/CreateProjectDialog.tsx
git commit -m "feat(ui): restyle projects page and create dialog"
```

### Task 19: `ResourceTable`

**Files:**
- Modify: `src/features/components/ResourceTable.tsx`
- Check: `src/features/components/ResourceTable.test.tsx`

- [ ] **Step 1: Update classes in `ResourceTable.tsx`**

Replace the empty-state line, `thead`, and `tbody`:

```tsx
  if (rows.length === 0) {
    return <p className="text-sm text-subtle">{empty ?? "Nothing here yet."}</p>;
  }
```

```tsx
      <thead className="border-b border-line text-xs uppercase tracking-wide text-subtle">
```

```tsx
      <tbody className="divide-y divide-line">
        {rows.map((row) => (
          <tr key={rowKey(row)} className="hover:bg-surface-hover">
```

(Keep column/actions rendering logic unchanged.)

- [ ] **Step 2: Run the table test**

Run: `pnpm test -- src/features/components/ResourceTable.test.tsx`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add ui/src/features/components/ResourceTable.tsx
git commit -m "feat(ui): restyle resource table"
```

### Task 20: `ConfirmDialog` + `SetSecretValueDialog` (onto Dialog)

**Files:**
- Modify: `src/features/components/ConfirmDialog.tsx`
- Modify: `src/features/manage/SetSecretValueDialog.tsx`
- Check: `src/features/components/ConfirmDialog.test.tsx`, `src/features/manage/SecretsPage.test.tsx`

- [ ] **Step 1: Replace `ConfirmDialog.tsx`**

```tsx
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";

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
    <Dialog title={title} onClose={onClose}>
      <div className="space-y-3">
        <p className="text-sm text-muted">{message}</p>
        {error && <p className="text-xs text-danger">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button type="button" variant="danger" size="sm" loading={pending} onClick={() => void onConfirm()}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
```

- [ ] **Step 2: Replace `SetSecretValueDialog.tsx`**

```tsx
import { useState } from "react";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { Field, Input } from "../../ui/Field";
import { useSetSecretValue } from "./useSecrets";

export function SetSecretValueDialog({ secretId, secretName, onClose }: { secretId: string; secretName: string; onClose: () => void }) {
  const [value, setValue] = useState("");
  const setVal = useSetSecretValue();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (value === "") return;
    try {
      await setVal.mutateAsync({ id: secretId, value });
      setValue("");
      onClose();
    } catch {
      setValue("");
    }
  }

  const is503 = (setVal.error as { status?: number } | null)?.status === 503;

  return (
    <Dialog title={`Set value — ${secretName}`} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <Field label="Value">
          <Input type="password" autoComplete="off" value={value} onChange={(e) => setValue(e.target.value)} />
        </Field>
        <p className="text-xs text-subtle">The value is write-only — it is stored encrypted and never shown again.</p>
        {setVal.isError && (
          <p className="text-xs text-danger">
            {is503 ? "Secret encryption key not configured on the server." : (setVal.error as Error).message}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button type="submit" size="sm" disabled={value === ""} loading={setVal.isPending}>Save</Button>
        </div>
      </form>
    </Dialog>
  );
}
```

- [ ] **Step 3: Run affected tests**

Run: `pnpm test -- src/features/components/ConfirmDialog.test.tsx src/features/manage/SecretsPage.test.tsx`
Expected: PASS (Cancel/Delete/Save button names + messages preserved).

- [ ] **Step 4: Commit**

```bash
git add ui/src/features/components/ConfirmDialog.tsx ui/src/features/manage/SetSecretValueDialog.tsx
git commit -m "feat(ui): move confirm and secret dialogs onto Dialog primitive"
```

### Task 21: `SecretsPage`

**Files:**
- Modify: `src/features/manage/SecretsPage.tsx`
- Check: `src/features/manage/SecretsPage.test.tsx`

- [ ] **Step 1: Apply primitives + tokens in `SecretsPage.tsx`**

Add imports at the top:
```tsx
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { Field, Input } from "../../ui/Field";
```

Header:
```tsx
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-fg">Secrets</h1>
        <Button size="sm" onClick={() => setCreating(true)}>New secret</Button>
      </div>
```

Loading/error:
```tsx
      {isLoading && <p className="text-sm text-subtle">Loading…</p>}
      {isError && <p className="text-sm text-danger">{(error as Error).message}</p>}
```

Description + Status columns:
```tsx
          { header: "Description", render: (s) => <span className="text-muted">{s.description}</span> },
          { header: "Status", render: (s) => (s.has_value ? <span className="text-success">● configured</span> : <span className="text-subtle">○ empty</span>) },
```

Actions:
```tsx
        actions={(s) => (
          <div className="flex justify-end gap-3 text-sm">
            <button onClick={() => setValueFor(s)} className="text-accent hover:underline">Set value</button>
            <button onClick={() => setDeleting(s)} className="text-danger hover:underline">Delete</button>
          </div>
        )}
```

Replace the inline create modal (`{creating && ( … )}`) with a `Dialog`:
```tsx
      {creating && (
        <Dialog title="New secret" onClose={() => setCreating(false)}>
          <form onSubmit={submitCreate} className="space-y-3">
            <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
            <Field label="Description"><Input value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
            {create.isError && <p className="text-xs text-danger">{(create.error as Error).message}</p>}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" size="sm" onClick={() => setCreating(false)}>Cancel</Button>
              <Button type="submit" size="sm" disabled={name.trim() === ""} loading={create.isPending}>Create</Button>
            </div>
          </form>
        </Dialog>
      )}
```

- [ ] **Step 2: Run the test**

Run: `pnpm test -- src/features/manage/SecretsPage.test.tsx`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add ui/src/features/manage/SecretsPage.tsx
git commit -m "feat(ui): restyle secrets page"
```

### Task 22: `SkillsPage`

**Files:**
- Modify: `src/features/manage/SkillsPage.tsx`
- Check: `src/features/manage/SkillsPage.test.tsx`

- [ ] **Step 1: Apply the same pattern as Task 21**

Add imports:
```tsx
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { Field, Input } from "../../ui/Field";
```

Header → `<Button size="sm" onClick={openNew}>New skill</Button>`; loading `text-subtle`; error `text-danger`; the three column renders use `text-muted`; actions buttons → `text-accent hover:underline` (Edit) and `text-danger hover:underline` (Delete).

Replace the inline `{editing && ( … )}` modal with:
```tsx
      {editing && (
        <Dialog title={editing === "new" ? "New skill" : "Edit skill"} onClose={() => setEditing(null)}>
          <form onSubmit={submit} className="space-y-3">
            <Field label="Name"><Input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></Field>
            <Field label="Description"><Input value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></Field>
            <Field label="Source"><Input value={draft.source} onChange={(e) => setDraft({ ...draft, source: e.target.value })} /></Field>
            {mutError && <p className="text-xs text-danger">{mutError.message}</p>}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(null)}>Cancel</Button>
              <Button type="submit" size="sm" disabled={draft.name.trim() === ""} loading={mutating}>
                {editing === "new" ? "Create" : "Save"}
              </Button>
            </div>
          </form>
        </Dialog>
      )}
```

- [ ] **Step 2: Run the test**

Run: `pnpm test -- src/features/manage/SkillsPage.test.tsx`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add ui/src/features/manage/SkillsPage.tsx
git commit -m "feat(ui): restyle skills page"
```

### Task 23: `McpServersPage`

**Files:**
- Modify: `src/features/manage/McpServersPage.tsx`
- Check: `src/features/manage/McpServersPage.test.tsx`

- [ ] **Step 1: Apply the same pattern**

Add imports:
```tsx
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { Field, Input, Select } from "../../ui/Field";
```

Header → `<Button size="sm" onClick={openNew}>New MCP server</Button>`; loading `text-subtle`; error `text-danger`; the four column renders use `text-muted`; actions → `text-accent hover:underline` / `text-danger hover:underline`.

Replace the inline `{editing && ( … )}` modal with a `Dialog` (keep the tool-allowlist logic; only swap chrome + controls). Use `Field`/`Input` for Name, Command/URL, and Add-tool, and `Field`/`Select` for Transport. The allowlist chips become:
```tsx
            <div className="flex flex-wrap gap-1">
              {draft.tool_allowlist.map((t) => (
                <span key={t} className="flex items-center gap-1 rounded-full bg-surface-hover px-2 py-0.5 text-xs text-muted">
                  {t}
                  <button type="button" aria-label={`remove ${t}`} onClick={() => removeTool(t)} className="text-subtle hover:text-fg">✕</button>
                </span>
              ))}
            </div>
```
The Transport field becomes:
```tsx
            <Field label="Transport">
              <Select value={draft.transport} onChange={(e) => setDraft({ ...draft, transport: e.target.value as McpTransport })}>
                <option value="stdio">stdio</option>
                <option value="http">http</option>
              </Select>
            </Field>
```
Footer buttons mirror Task 22 (`Cancel` ghost, submit primary with `loading={mutating}`, label `editing === "new" ? "Create" : "Save"`). Wrap everything in `<Dialog title={editing === "new" ? "New MCP server" : "Edit MCP server"} onClose={() => setEditing(null)}>`.

- [ ] **Step 2: Run the test**

Run: `pnpm test -- src/features/manage/McpServersPage.test.tsx`
Expected: PASS (including the `remove <tool>` aria-label).

- [ ] **Step 3: Commit**

```bash
git add ui/src/features/manage/McpServersPage.tsx
git commit -m "feat(ui): restyle MCP servers page"
```

### Task 24: Runs — `RunStatusBadge`, `RunActions`, `RunSection`, `MemoryProposalCard`

**Files:**
- Modify: `src/features/runs/RunStatusBadge.tsx`
- Modify: `src/features/runs/RunActions.tsx`
- Modify: `src/features/runs/RunSection.tsx`
- Modify: `src/features/runs/MemoryProposalCard.tsx`
- Check: `src/features/runs/RunActions.test.tsx`, `src/features/runs/RunSection.test.tsx`, `src/features/runs/MemoryProposalCard.test.tsx`

- [ ] **Step 1: Replace `RunStatusBadge.tsx` (map onto Badge tones)**

```tsx
import { Badge, type BadgeTone } from "../../ui/Badge";
import type { RunStatus } from "../../lib/api/types";

const TONES: Record<RunStatus, BadgeTone> = {
  pending: "neutral",
  running: "info",
  awaiting_approval: "warning",
  done: "success",
  failed: "danger",
  blocked: "warning",
  cancelled: "neutral",
};

export function RunStatusBadge({ status }: { status: RunStatus }) {
  return <Badge tone={TONES[status]}>{status}</Badge>;
}
```

- [ ] **Step 2: Replace `RunActions.tsx` (Button + Input)**

```tsx
import { useState } from "react";
import { Button } from "../../ui/Button";
import { Input } from "../../ui/Field";
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
            <Button size="sm" onClick={() => approve.mutate()}>Approve</Button>
            <Button size="sm" variant="danger" onClick={() => reject.mutate()}>Reject</Button>
          </>
        )}
        {!isTerminal && (
          <Button size="sm" variant="secondary" onClick={() => cancel.mutate()}>Cancel</Button>
        )}
        <Button size="sm" variant="secondary" onClick={() => setEditing((v) => !v)}>Edit</Button>
      </div>
      {editing && (
        <div className="space-y-1">
          <Input className="text-xs" placeholder="branch" value={branch} onChange={(e) => setBranch(e.target.value)} />
          <Input className="text-xs" placeholder="stage" value={stage} onChange={(e) => setStage(e.target.value)} />
          <Button
            size="sm"
            onClick={() => { edit.mutate({ branch: branch || undefined, stage: stage || undefined }); setEditing(false); }}
          >
            Save fields
          </Button>
        </div>
      )}
      {(cancel.isError || approve.isError || reject.isError || edit.isError) && (
        <p className="text-xs text-danger">Action failed.</p>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Restyle `RunSection.tsx`**

Add `import { Button } from "../../ui/Button";` at the top. Replace the header `<h3>`, Run button, error/loading lines, and the list item:

```tsx
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-subtle">Runs</h3>
        <Button
          size="sm"
          disabled={taskStatus !== "ready" || start.isPending}
          title={taskStatus !== "ready" ? "Task must be Ready to run" : undefined}
          onClick={() => start.mutate()}
        >
          Run
        </Button>
      </div>
      {start.isError && <p className="text-sm text-danger">{(start.error as Error).message}</p>}
      {isLoading && <p className="text-sm text-subtle">Loading runs…</p>}
      <ul className="space-y-2">
        {data?.map((run) => (
          <li key={run.id} className="rounded-md border border-line bg-surface p-2 text-sm">
            <div className="flex items-center justify-between">
              <RunStatusBadge status={run.status} />
              <span className="text-xs text-subtle">{run.stage ?? "—"}</span>
            </div>
            <RunActions taskId={taskId} run={run} />
            <MemoryProposalCard runId={run.id} />
          </li>
        ))}
      </ul>
```

- [ ] **Step 4: Restyle `MemoryProposalCard.tsx`** (keep all logic; swap chrome to status tokens and `Button`)

```tsx
import { useState } from "react";
import { Button } from "../../ui/Button";
import { useMemoryProposal } from "./useMemoryProposal";

export function MemoryProposalCard({ runId }: { runId: string }) {
  const { query, apply, reject } = useMemoryProposal(runId);
  const [open, setOpen] = useState(false);
  const proposal = query.data;

  if (query.isLoading || !proposal) return null;

  const isProposed = proposal.status === "proposed";

  return (
    <div className="mt-2 rounded-md border border-warning/40 bg-warning-subtle p-2 text-xs">
      <div className="flex items-center justify-between">
        <span className="font-semibold text-warning">Memory proposal · {proposal.files.length} file(s)</span>
        <span className="rounded-full bg-warning/20 px-1.5 py-0.5 text-warning">{proposal.status}</span>
      </div>
      <ul className="mt-1 list-disc pl-4 text-muted">
        {proposal.files.map((f) => (
          <li key={f}>{f}</li>
        ))}
      </ul>
      <button className="mt-1 text-accent hover:underline" onClick={() => setOpen((v) => !v)}>
        {open ? "Hide diff" : "Show diff"}
      </button>
      {open && (
        <pre className="mt-1 max-h-64 overflow-auto rounded bg-surface p-2 text-[11px] text-fg">{proposal.diff}</pre>
      )}
      {isProposed && (
        <div className="mt-2 flex gap-2">
          <Button size="sm" onClick={() => apply.mutate()} loading={apply.isPending}>Apply</Button>
          <Button size="sm" variant="danger" onClick={() => reject.mutate()} loading={reject.isPending}>Reject</Button>
        </div>
      )}
      {proposal.pr_url && (
        <a className="mt-1 block text-accent hover:underline" href={proposal.pr_url}>View PR</a>
      )}
      {(apply.isError || reject.isError) && <p className="mt-1 text-danger">Action failed.</p>}
    </div>
  );
}
```

- [ ] **Step 5: Run run tests**

Run: `pnpm test -- src/features/runs`
Expected: PASS (status text, Approve/Reject/Cancel/Edit/Save fields/Apply/Reject labels, "Action failed." preserved).

- [ ] **Step 6: Commit**

```bash
git add ui/src/features/runs/
git commit -m "feat(ui): restyle runs section, actions, status badge, memory card"
```

### Task 25: `ChatRail`

**Files:**
- Modify: `src/features/chat/ChatRail.tsx`
- Check: `src/features/chat/ChatRail.test.tsx`

- [ ] **Step 1: Replace `ChatRail.tsx`**

```tsx
import { useState } from "react";
import { Button } from "../../ui/Button";
import { Input } from "../../ui/Field";
import { useChat } from "./useChat";

interface ChatRailProps {
  projectId: string;
}

export function ChatRail({ projectId }: ChatRailProps) {
  const { turns, send } = useChat(projectId);
  const [text, setText] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed) return;
    send.mutate(trimmed);
    setText("");
  };

  return (
    <aside className="flex h-full w-80 shrink-0 flex-col border-l border-line bg-panel">
      <h2 className="border-b border-line p-2 text-sm font-semibold text-fg">Team lead</h2>
      <div className="flex-1 space-y-2 overflow-y-auto p-2 text-sm">
        {turns.map((t, i) => (
          <div key={i} className={t.role === "user" ? "text-right" : ""}>
            <span
              className={`inline-block rounded-lg px-2 py-1 ${
                t.role === "user" ? "bg-accent text-accent-fg" : "bg-surface text-fg"
              }`}
            >
              {t.content}
            </span>
          </div>
        ))}
      </div>
      <form className="flex gap-1 border-t border-line p-2" onSubmit={handleSubmit}>
        <Input
          placeholder="Message the team lead…"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <Button type="submit" size="sm" loading={send.isPending}>Send</Button>
      </form>
    </aside>
  );
}
```

- [ ] **Step 2: Run the test**

Run: `pnpm test -- src/features/chat/ChatRail.test.tsx`
Expected: PASS (placeholder + Send button + turn text preserved).

- [ ] **Step 3: Commit**

```bash
git add ui/src/features/chat/ChatRail.tsx
git commit -m "feat(ui): restyle chat rail"
```

### Task 26: `HierarchyTree` + `AcceptanceCriteria`

**Files:**
- Modify: `src/features/work-items/HierarchyTree.tsx`
- Modify: `src/features/work-items/AcceptanceCriteria.tsx`

- [ ] **Step 1: Apply tokens + primitives in `HierarchyTree.tsx`**

Add `import { Button } from "../../ui/Button";` and `import { Input, Select } from "../../ui/Field";`. Then:
- container: `className="w-60 shrink-0 border-r border-line bg-panel p-3 text-sm"`
- epic title span → `className="font-medium text-fg"`
- "All tasks" button → `className="mb-2 block text-left text-xs text-accent hover:underline"`
- feature button selected state → `className={\`text-left ${selectedFeature === f.id ? "text-accent underline" : "text-muted hover:text-fg"}\`}`
- "+ Add epic" / "+ Add feature" buttons → `className="block text-xs text-accent hover:underline"`
- the add panel wrapper → `className="mt-2 space-y-2 rounded-md border border-line bg-surface p-2"`
- the epic `<select … >` → `<Select … >` (keep the same value/onChange and `<option>` children)
- the title `<input … />` → `<Input … />`
- Create button → `<Button size="sm" onClick={submit}>Create</Button>`
- Cancel button → `<Button size="sm" variant="ghost" onClick={() => setAdding(null)}>Cancel</Button>`

- [ ] **Step 2: Apply tokens + Input in `AcceptanceCriteria.tsx`**

Add `import { Input } from "../../ui/Field";`. Replace the criterion `<input … />` with `<Input className="text-sm" … />` (keep value/onChange/placeholder), the remove `<button>` class with `text-sm text-danger hover:text-danger/80`, and the add `<button>` class with `text-sm text-accent hover:underline`.

- [ ] **Step 3: Run work-item + board tests**

Run: `pnpm test -- src/features/work-items src/features/board`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add ui/src/features/work-items/HierarchyTree.tsx ui/src/features/work-items/AcceptanceCriteria.tsx
git commit -m "feat(ui): restyle hierarchy tree and acceptance criteria"
```

### Task 27: `BoardPage` chrome

**Files:**
- Modify: `src/features/board/BoardPage.tsx`

- [ ] **Step 1: Restyle the header in `BoardPage.tsx`**

Add `import { Button } from "../../ui/Button";`. Replace the `<header>` block:

```tsx
      <header className="flex items-center gap-3 border-b border-line bg-surface px-4 py-3">
        <Link to="/" className="text-sm text-accent hover:underline">← Projects</Link>
        <h1 className="font-semibold text-fg">Board</h1>
        <div className="ml-auto flex items-center gap-2">
          <Button size="sm" variant="secondary" onClick={() => setShowChat((v) => !v)}>
            {showChat ? "Hide chat" : "Team lead"}
          </Button>
        </div>
      </header>
```

(Leave the body/panel logic unchanged.)

- [ ] **Step 2: Run board tests**

Run: `pnpm test -- src/features/board`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add ui/src/features/board/BoardPage.tsx
git commit -m "feat(ui): restyle board page header"
```

### Task 28: Full verification + PR

**Files:** none (verification only)

- [ ] **Step 1: Full test suite**

Run: `pnpm test`
Expected: all suites PASS.

- [ ] **Step 2: Type/lint check**

Run: `pnpm lint`
Expected: PASS (tsc no-emit clean).

- [ ] **Step 3: Production build**

Run: `pnpm build`
Expected: build succeeds (tsc -b + vite build).

- [ ] **Step 4: Manual dark/light smoke**

Run `pnpm dev`, open the app, and verify in both themes (toggle in header): projects grid, board (drag a card), a manage page + its create dialog, runs section, chat rail. Confirm no flash on reload, readable contrast, and consistent surfaces.

- [ ] **Step 5: Open the PR**

```bash
git push -u origin feat/ui-modern-redesign
gh pr create --title "feat(ui): modern dev-tool redesign with dark/light theming" \
  --body "Adds a design-token system (light + dark), dependency-free UI primitives, and restyles every surface. See docs/superpowers/specs/2026-06-14-ui-modern-redesign-design.md and docs/superpowers/plans/2026-06-14-ui-modern-redesign.md."
```

---

## Self-Review Notes

- **Spec coverage:** tokens+theming (Tasks 1–3, 5–6), primitives (Tasks 4, 7–13), all surfaces in the spec's "Surfaces to Restyle" list (Tasks 14–27), testing + 80% gate (Task 28). No spec requirement is unaddressed.
- **Dependency order:** `Button` needs `Spinner` (do Task 7 before 8); `ThemeToggle` needs `IconButton` (do Task 13 before Task 6, or stub a plain button). Surface tasks depend on all primitives — execute Phase 1 fully before Phase 2.
- **Type consistency:** `Badge` exports `BadgeTone`, consumed by `RunStatusBadge`. `Field` exports `Input`/`Textarea`/`Select`/`Field`, consumed across dialogs and forms. `cn` signature stable. Token utility names match the reference table everywhere.
- **No behavior change:** restyle tasks preserve roles, accessible names, button labels, and visible text, so existing Testing-Library tests stay green.
