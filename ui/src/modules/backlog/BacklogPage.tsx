import { useParams } from "react-router-dom";
import { EmptyState } from "@/components/ui/EmptyState";
import { EpicRow } from "./EpicRow";
import { useBacklog } from "./useBacklog";

export default function BacklogPage() {
  const { projectId = "" } = useParams();
  const { query, activate, deactivate, setCap } = useBacklog(projectId);
  const data = query.data;
  const busy = activate.isPending || deactivate.isPending || setCap.isPending;

  if (query.isLoading) return <p className="p-6 text-sm text-subtle">Loading…</p>;
  if (query.isError)
    return <p className="p-6 text-sm text-danger">{(query.error as Error).message}</p>;
  if (!data) return null;

  const activeEpics = data.epics.filter((e) => e.active);
  const backlogEpics = data.epics.filter((e) => !e.active);

  return (
    <div className="mx-auto max-w-4xl p-6">
      <div className="mb-6 flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight text-fg">Backlog</h1>
        <label className="flex items-center gap-2 text-sm text-muted">
          Max concurrent runs
          <input
            type="number"
            min={1}
            defaultValue={data.max_concurrent_runs}
            onBlur={(e) => {
              const v = Number(e.target.value);
              if (v >= 1 && v !== data.max_concurrent_runs) setCap.mutate(v);
            }}
            className="w-16 rounded-md border border-line bg-surface px-2 py-1 text-fg"
          />
        </label>
      </div>
      <p className="mb-4 text-xs text-subtle">
        running {data.in_flight} / {data.max_concurrent_runs} · queued {data.queued}
      </p>

      {data.epics.length === 0 && (
        <EmptyState
          title="No epics yet"
          description="Create epics on the board, then activate them here to start work."
        />
      )}

      {activeEpics.length > 0 && (
        <section className="mb-6">
          <h2 className="mb-2 text-sm font-semibold text-muted">Active</h2>
          <div className="grid gap-3">
            {activeEpics.map((e) => (
              <EpicRow
                key={e.epic.id}
                projectId={projectId}
                item={e}
                busy={busy}
                onActivate={() => activate.mutate(e.epic.id)}
                onDeactivate={() => deactivate.mutate(e.epic.id)}
              />
            ))}
          </div>
        </section>
      )}

      {backlogEpics.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-semibold text-muted">Backlog</h2>
          <div className="grid gap-3">
            {backlogEpics.map((e) => (
              <EpicRow
                key={e.epic.id}
                projectId={projectId}
                item={e}
                busy={busy}
                onActivate={() => activate.mutate(e.epic.id)}
                onDeactivate={() => deactivate.mutate(e.epic.id)}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
