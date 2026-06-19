import type { ReactNode } from "react";
import { cn } from "./cn";

/** A bordered, divided container for a vertical list of rows. */
export function ListSection({
  title,
  action,
  children,
  className,
}: {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={className}>
      {(title || action) && (
        <div className="mb-2 flex items-center justify-between gap-3">
          {title && <h2 className="text-sm font-semibold text-muted">{title}</h2>}
          {action}
        </div>
      )}
      <div className="divide-y divide-line overflow-hidden rounded-md border border-line">
        {children}
      </div>
    </section>
  );
}

/** A single full-width list row. Clickable when `onClick` is provided. */
export function ListRow({
  onClick,
  className,
  children,
}: {
  onClick?: () => void;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      onClick={onClick}
      className={cn(
        "flex items-center gap-3 bg-surface px-3 py-2.5 transition-colors",
        onClick && "cursor-pointer hover:bg-surface-hover",
        className,
      )}
    >
      {children}
    </div>
  );
}
