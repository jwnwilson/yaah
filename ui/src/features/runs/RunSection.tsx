import { useRuns } from "./useRuns";
import { useStartRun } from "./useStartRun";
import { RunStatusBadge } from "./RunStatusBadge";
import { RunActions } from "./RunActions";
import type { WorkItemStatus } from "../../lib/api/types";

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
        <h3 className="text-xs font-semibold uppercase text-gray-500">Runs</h3>
        <button
          className="rounded bg-emerald-600 px-3 py-1 text-sm text-white disabled:opacity-50"
          disabled={taskStatus !== "ready" || start.isPending}
          title={taskStatus !== "ready" ? "Task must be Ready to run" : undefined}
          onClick={() => start.mutate()}
        >
          Run
        </button>
      </div>
      {start.isError && <p className="text-sm text-red-600">{(start.error as Error).message}</p>}
      {isLoading && <p className="text-sm text-gray-500">Loading runs…</p>}
      <ul className="space-y-2">
        {data?.map((run) => (
          <li key={run.id} className="rounded border p-2 text-sm">
            <div className="flex items-center justify-between">
              <RunStatusBadge status={run.status} />
              <span className="text-xs text-gray-500">{run.stage ?? "—"}</span>
            </div>
            <RunActions taskId={taskId} run={run} />
          </li>
        ))}
      </ul>
    </div>
  );
}
