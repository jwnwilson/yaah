import type { ReactNode } from "react";

/** Slim per-page header: a title and optional right-aligned page actions. Project/section
 * navigation lives in the sidebar, so this stays minimal. */
export function PageHeader({ title, actions }: { title: ReactNode; actions?: ReactNode }) {
  return (
    <header className="flex items-center gap-3 border-b border-line bg-surface px-4 py-3">
      <h1 className="font-semibold text-fg">{title}</h1>
      {actions && <div className="ml-auto flex items-center gap-3">{actions}</div>}
    </header>
  );
}
