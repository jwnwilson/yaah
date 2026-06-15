import type { RunStatus } from "@/lib/api/types";
import { Badge, type BadgeTone } from "@/ui/Badge";

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
