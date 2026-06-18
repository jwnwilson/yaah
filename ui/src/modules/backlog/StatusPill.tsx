import type { BadgeTone } from "@/components/ui/Badge";
import { cn } from "@/components/ui/cn";
import type { WorkItemStatus } from "@/lib/api/types";

const STATUSES: WorkItemStatus[] = [
  "draft",
  "refining",
  "ready",
  "in_progress",
  "in_review",
  "approved",
  "done",
  "blocked",
  "failed",
];

const TONE: Record<WorkItemStatus, BadgeTone> = {
  draft: "neutral",
  refining: "neutral",
  ready: "info",
  in_progress: "warning",
  in_review: "warning",
  approved: "success",
  done: "success",
  blocked: "danger",
  failed: "danger",
};

const TONE_CLASS: Record<BadgeTone, string> = {
  neutral: "bg-surface-hover text-muted",
  success: "bg-success-subtle text-success",
  warning: "bg-warning-subtle text-warning",
  danger: "bg-danger-subtle text-danger",
  info: "bg-info-subtle text-info",
  accent: "bg-accent-subtle text-accent",
};

/** A status badge that doubles as a dropdown (a transparent <select> overlay). */
export function StatusPill({
  status,
  onChange,
}: {
  status: WorkItemStatus;
  onChange: (s: WorkItemStatus) => void;
}) {
  const label = status.replace(/_/g, " ");
  return (
    <span
      className={cn(
        "relative inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium capitalize",
        TONE_CLASS[TONE[status]],
      )}
    >
      {label}
      <select
        aria-label="status"
        value={status}
        onClick={(e) => e.stopPropagation()}
        onChange={(e) => onChange(e.target.value as WorkItemStatus)}
        className="absolute inset-0 cursor-pointer opacity-0"
      >
        {STATUSES.map((s) => (
          <option key={s} value={s}>
            {s.replace(/_/g, " ")}
          </option>
        ))}
      </select>
    </span>
  );
}
