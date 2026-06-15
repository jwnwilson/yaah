import type { WorkItemStatus } from "@/lib/api/types";
import { Button } from "@/ui/Button";
import { MemoryProposalCard } from "./MemoryProposalCard";
import { RunActions } from "./RunActions";
import { RunStatusBadge } from "./RunStatusBadge";
import { useRuns } from "./useRuns";
import { useStartRun } from "./useStartRun";

export function RunSection({
  projectId,
  taskId,
  taskStatus,
}: {
  projectId: string;
  taskId: string;
  taskStatus: WorkItemStatus;
}) {
  const { data, isLoading } = useRuns(taskId);
  const start = useStartRun(projectId, taskId);

  return (
    <div>
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
    </div>
  );
}
