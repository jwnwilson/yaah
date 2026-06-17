import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/components/ui/cn";
import type { AuditEvent } from "@/lib/api/types";
import { AuditDecisionRow, RunEventRow } from "./RunEventRow";
import type { Round, StageBucket } from "./runTimeline";

function GrantSummary({ grant }: { grant: AuditEvent }) {
  const detail = grant.detail ?? {};
  const parts: string[] = [];
  for (const key of ["tools", "skills", "mcp", "model"]) {
    const value = detail[key];
    if (Array.isArray(value) && value.length) parts.push(`${key}: ${value.join(", ")}`);
    else if (typeof value === "string" && value) parts.push(`${key}: ${value}`);
  }
  return (
    <div className="rounded-md border border-line bg-surface-hover px-2 py-1 text-xs text-muted">
      <span className="font-medium text-fg">Capabilities</span>
      {parts.length ? ` — ${parts.join(" · ")}` : " granted"}
    </div>
  );
}

function StagePanel({ bucket }: { bucket: StageBucket }) {
  return (
    <div className="space-y-1 border-l-2 border-line pl-3">
      <div className="text-xs font-semibold uppercase tracking-wide text-subtle">
        {bucket.stage ?? "—"}
      </div>
      {bucket.grant && <GrantSummary grant={bucket.grant} />}
      {bucket.milestones.map((event) => (
        <RunEventRow key={event.id} event={event} />
      ))}
      {bucket.narration.map((event) => (
        <RunEventRow key={event.id} event={event} />
      ))}
      {bucket.decisions.map((audit) => (
        <AuditDecisionRow key={audit.id} audit={audit} />
      ))}
    </div>
  );
}

export function RoundGroup({ round, defaultExpanded = false }: { round: Round; defaultExpanded?: boolean }) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const milestones = round.stages.flatMap((s) => s.milestones);

  return (
    <section className="rounded-lg border border-line bg-surface">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left"
      >
        <span className="flex items-center gap-2">
          <span className={cn("text-subtle transition-transform", expanded && "rotate-90")} aria-hidden>
            ▸
          </span>
          <span className="font-medium text-fg">{round.label}</span>
        </span>
        <Badge tone="neutral">{milestones.length} milestones</Badge>
      </button>

      <div className="border-t border-line px-3 py-2">
        {expanded ? (
          <div className="space-y-3">
            {round.stages.map((bucket) => (
              <StagePanel key={String(bucket.stage)} bucket={bucket} />
            ))}
          </div>
        ) : (
          <div>
            {milestones.length === 0 ? (
              <p className="text-sm text-subtle">No milestones yet.</p>
            ) : (
              milestones.map((event) => <RunEventRow key={event.id} event={event} />)
            )}
          </div>
        )}
      </div>
    </section>
  );
}
