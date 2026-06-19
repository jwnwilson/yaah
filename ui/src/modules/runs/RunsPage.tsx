import { Link } from "react-router-dom";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { Spinner } from "@/components/ui/Spinner";
import { relativeTime } from "./RunEventRow";
import { RunStatusBadge } from "./RunStatusBadge";
import { useAllRuns } from "./useAllRuns";

export function RunsPage() {
  const { data, isLoading } = useAllRuns();
  const rows = data ?? [];

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Runs" />
      <div className="flex-1 overflow-auto p-4">
      {isLoading && (
        <div className="flex justify-center py-12 text-muted">
          <Spinner />
        </div>
      )}
      {!isLoading && rows.length === 0 && (
        <EmptyState title="No runs yet" description="Start a run from a ticket to see it here." />
      )}
      {rows.length > 0 && (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-subtle">
              <th className="py-2">Task</th>
              <th>Status</th>
              <th>Stage</th>
              <th>Cost</th>
              <th>Started</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((run) => (
              <tr key={run.id} className="border-b border-line align-top">
                <td className="py-2">
                  <Link to={`/runs/${run.id}`} className="text-accent hover:underline">
                    {run.task_title ?? run.task_id}
                  </Link>
                </td>
                <td>
                  <RunStatusBadge status={run.status} />
                </td>
                <td className="text-muted">{run.stage ?? "—"}</td>
                <td className="text-muted">${run.cost_usd.toFixed(2)}</td>
                <td className="text-muted">{relativeTime(run.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      </div>
    </div>
  );
}
