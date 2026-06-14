import { useState } from "react";
import type { MemoryProposalStatus } from "../../lib/api/memory";
import { MemoryDiff } from "../runs/MemoryDiff";
import { useMemoryProposals } from "./useMemoryProposals";

const STATUSES: MemoryProposalStatus[] = ["proposed", "applied", "rejected"];

const badgeClass: Record<MemoryProposalStatus, string> = {
  proposed: "bg-amber-100 text-amber-800",
  applied: "bg-green-100 text-green-800",
  rejected: "bg-gray-200 text-gray-700",
};

export function MemoryPage() {
  const [status, setStatus] = useState<MemoryProposalStatus | "">("");
  const { data, isLoading, isError, error } = useMemoryProposals(status ? { status } : {});
  const rows = data?.data ?? [];

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Memory proposals</h1>
        <label className="text-sm">
          Status{" "}
          <select className="rounded border p-1" value={status}
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
      {isLoading && <p className="text-sm text-gray-500">Loading…</p>}
      {isError && <p className="text-sm text-red-600">{(error as Error).message}</p>}
      {!isLoading && rows.length === 0 && <p className="text-sm text-gray-500">No memory proposals.</p>}
      <ul className="space-y-3">
        {rows.map((p) => (
          <li key={p.id} className="rounded border p-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="font-medium">{p.files.join(", ")}</span>
              <span className={`rounded px-1.5 py-0.5 text-xs ${badgeClass[p.status]}`}>{p.status}</span>
            </div>
            <div className="mt-1 text-xs text-gray-500">
              project {p.project_id} · {new Date(p.created_at).toLocaleString()}
            </div>
            <div className="mt-2"><MemoryDiff diff={p.diff} /></div>
            {p.pr_url && (
              <a className="mt-1 block text-blue-700 underline" href={p.pr_url}>View PR</a>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
