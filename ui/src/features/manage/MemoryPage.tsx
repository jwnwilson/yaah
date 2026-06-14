import { useState } from "react";
import type { MemoryProposalStatus } from "../../lib/api/memory";
import { Badge, type BadgeTone } from "../../ui/Badge";
import { MemoryDiff } from "../runs/MemoryDiff";
import { useMemoryProposals } from "./useMemoryProposals";

const STATUSES: MemoryProposalStatus[] = ["proposed", "applied", "rejected"];

const statusTone: Record<MemoryProposalStatus, BadgeTone> = {
  proposed: "warning",
  applied: "success",
  rejected: "neutral",
};

export function MemoryPage() {
  const [status, setStatus] = useState<MemoryProposalStatus | "">("");
  const { data, isLoading, isError, error } = useMemoryProposals(status ? { status } : {});
  const rows = data?.data ?? [];

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-fg">Memory proposals</h1>
        <label className="text-sm">
          Status{" "}
          <select className="rounded-md border border-line bg-surface px-2 py-1 text-sm text-fg" value={status}
            onChange={(e) => setStatus(e.target.value as MemoryProposalStatus | "")}>
            <option value="">All</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </option>
            ))}
          </select>
        </label>
      </div>
      {isLoading && <p className="text-sm text-subtle">Loading…</p>}
      {isError && <p className="text-sm text-danger">{(error as Error).message}</p>}
      {!isLoading && rows.length === 0 && <p className="text-sm text-subtle">No memory proposals.</p>}
      <ul className="space-y-3">
        {rows.map((p) => (
          <li key={p.id} className="rounded-md border border-line bg-surface p-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="font-medium">{p.files.join(", ")}</span>
              <Badge tone={statusTone[p.status]}>{p.status}</Badge>
            </div>
            <div className="mt-1 text-xs text-subtle">
              project {p.project_id} · {new Date(p.created_at).toLocaleString()}
            </div>
            <div className="mt-2"><MemoryDiff diff={p.diff} /></div>
            {p.pr_url && (
              <a className="mt-1 block text-accent hover:underline" href={p.pr_url}>View PR</a>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
