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
