import type { ReactNode } from "react";

interface StatusChipProps {
  children: ReactNode;
}

export function StatusChip({ children }: StatusChipProps) {
  return (
    <div className="flex justify-center">
      <span className="rounded-full border border-line bg-surface px-2.5 py-0.5 text-xs text-muted">
        {children}
      </span>
    </div>
  );
}
