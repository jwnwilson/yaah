import { Link } from "react-router-dom";
import { cn } from "@/components/ui/cn";
import type { AuditEvent, RunEvent, RunEventType } from "@/lib/api/types";

// A small coloured dot per event/decision kind; danger for errors/denials.
const DOT_TONE: Record<string, string> = {
  stage_started: "bg-info",
  stage_completed: "bg-success",
  agent_dispatched: "bg-accent",
  agent_reported: "bg-accent",
  monitor_started: "bg-info",
  monitor_verdict: "bg-success",
  gate_opened: "bg-warning",
  gate_resolved: "bg-success",
  blocked: "bg-warning",
  quiescence_reached: "bg-muted",
  error: "bg-danger",
  // audit decision kinds
  tool_allowed: "bg-success",
  tool_denied: "bg-danger",
  capability_granted: "bg-accent",
};

const DANGER_KINDS: ReadonlySet<string> = new Set(["error", "tool_denied", "blocked"]);

export function relativeTime(iso: string, now: number = Date.now()): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diffSec = Math.round((now - then) / 1000);
  if (diffSec < 5) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  const min = Math.round(diffSec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  return `${Math.round(hr / 24)}d ago`;
}

function Dot({ kind }: { kind: string }) {
  return <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", DOT_TONE[kind] ?? "bg-muted")} aria-hidden />;
}

function Row({
  kind,
  message,
  createdAt,
  children,
}: {
  kind: string;
  message: string;
  createdAt: string;
  children?: React.ReactNode;
}) {
  const danger = DANGER_KINDS.has(kind);
  return (
    <div className={cn("flex items-start gap-2 py-1 text-sm", danger && "text-danger")}>
      <Dot kind={kind} />
      <div className="min-w-0 flex-1">{children ?? <span className="break-words">{message}</span>}</div>
      <time className="shrink-0 text-xs text-subtle" dateTime={createdAt}>
        {relativeTime(createdAt)}
      </time>
    </div>
  );
}

/** A single run-event row. `agent_dispatched` rows deep-link to the agent. */
export function RunEventRow({ event }: { event: RunEvent }) {
  const agentId = event.agent_id;
  if (event.type === ("agent_dispatched" satisfies RunEventType) && agentId) {
    return (
      <Row kind={event.type} message={event.message} createdAt={event.created_at}>
        <Link to={`/team/${agentId}`} className="text-accent hover:underline">
          {event.message || "View agent"}
        </Link>
      </Row>
    );
  }
  return <Row kind={event.type} message={event.message} createdAt={event.created_at} />;
}

function auditMessage(audit: AuditEvent): string {
  const detail = audit.detail ?? {};
  const tool = typeof detail.tool === "string" ? detail.tool : undefined;
  const reason = typeof detail.reason === "string" ? detail.reason : undefined;
  if (audit.action === "tool_allowed") return `allowed ${tool ?? "tool"}`;
  if (audit.action === "tool_denied") return `denied ${tool ?? "tool"}${reason ? ` — ${reason}` : ""}`;
  return audit.action;
}

/** A single tool allow/deny decision row. */
export function AuditDecisionRow({ audit }: { audit: AuditEvent }) {
  return <Row kind={audit.action} message={auditMessage(audit)} createdAt={audit.created_at} />;
}
