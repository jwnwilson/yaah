import { useNavigate, useParams } from "react-router-dom";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import type { Run, RunUsage } from "@/lib/api/types";
import { RoundGroup } from "./RoundGroup";
import { RunStatusBadge } from "./RunStatusBadge";
import { costByStage, segmentRounds } from "./runTimeline";
import { useRun, useRunAudit, useRunEvents, useRunUsage } from "./useRunInspector";

function fmtCost(n: number) {
  return `$${n.toFixed(2)}`;
}

function Header({ run }: { run: Run }) {
  const navigate = useNavigate();
  return (
    <div className="space-y-3">
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="text-sm text-accent hover:underline"
        title={`Back to ticket ${run.task_id}`}
      >
        ← Back to ticket
      </button>
      <div className="flex flex-wrap items-center gap-3">
        <RunStatusBadge status={run.status} />
        <span className="text-sm text-subtle">{run.stage ?? "—"}</span>
        <span className="text-sm font-semibold">{fmtCost(run.cost_usd)}</span>
        <span className="text-xs text-subtle">
          {run.input_tokens.toLocaleString()} in · {run.output_tokens.toLocaleString()} out
        </span>
        {run.branch && <span className="text-xs text-muted">branch: {run.branch}</span>}
        {run.pr_url && (
          <a href={run.pr_url} target="_blank" rel="noreferrer" className="text-xs text-accent hover:underline">
            PR
          </a>
        )}
      </div>
    </div>
  );
}

function CostTable({ usage }: { usage: RunUsage }) {
  const { perStage, total } = costByStage(usage);
  if (perStage.length === 0) return null;
  return (
    <Card className="overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-subtle">
            <th className="px-3 py-2">Stage</th>
            <th className="px-3 py-2">Cost</th>
            <th className="px-3 py-2">Input</th>
            <th className="px-3 py-2">Output</th>
          </tr>
        </thead>
        <tbody>
          {perStage.map((s) => (
            <tr key={s.stage} className="border-b border-line">
              <td className="px-3 py-2 font-medium">{s.stage}</td>
              <td className="px-3 py-2">{fmtCost(s.cost_usd)}</td>
              <td className="px-3 py-2">{s.input_tokens.toLocaleString()}</td>
              <td className="px-3 py-2">{s.output_tokens.toLocaleString()}</td>
            </tr>
          ))}
          <tr className="font-semibold">
            <td className="px-3 py-2">Total</td>
            <td className="px-3 py-2">{fmtCost(total.cost_usd)}</td>
            <td className="px-3 py-2">{total.input_tokens.toLocaleString()}</td>
            <td className="px-3 py-2">{total.output_tokens.toLocaleString()}</td>
          </tr>
        </tbody>
      </table>
    </Card>
  );
}

export function RunInspectorPage() {
  const { runId = "" } = useParams();
  const runQuery = useRun(runId);
  const run = runQuery.data;
  const eventsQuery = useRunEvents(runId, run);
  const usageQuery = useRunUsage(runId, run);
  const auditQuery = useRunAudit(runId, run);

  if (runQuery.isPending) {
    return (
      <div className="flex justify-center py-12">
        <Spinner />
      </div>
    );
  }

  if (runQuery.isError || !run) {
    return <p className="text-sm text-danger">{(runQuery.error as Error)?.message ?? "Run not found"}</p>;
  }

  const rounds = segmentRounds(eventsQuery.data ?? [], auditQuery.data ?? []);

  return (
    <div className="space-y-6">
      <Header run={run} />
      {usageQuery.data && <CostTable usage={usageQuery.data} />}
      {rounds.length === 0 ? (
        <EmptyState title="Waiting for the first round…" description="No orchestration rounds recorded yet." />
      ) : (
        <div className="space-y-3">
          {rounds.map((round, index) => (
            <RoundGroup key={round.key} round={round} defaultExpanded={index === rounds.length - 1} />
          ))}
        </div>
      )}
    </div>
  );
}
