import { useState } from "react";
import type { AuditAction } from "../../lib/api/audit";
import { useAudit } from "./useAudit";

const ACTIONS: AuditAction[] = ["capability_granted", "tool_allowed", "tool_denied"];

const badgeClass: Record<AuditAction, string> = {
  capability_granted: "bg-blue-100 text-blue-800",
  tool_allowed: "bg-green-100 text-green-800",
  tool_denied: "bg-red-100 text-red-800",
};

export function AuditPage() {
  const [action, setAction] = useState<AuditAction | "">("");
  const [page, setPage] = useState(1);
  const params = { page_number: page, ...(action ? { action } : {}) };
  const { data, isLoading, isError, error } = useAudit(params);
  const rows = data?.data ?? [];
  const total = data?.meta?.total ?? 0;
  const pageSize = data?.meta?.page_size ?? 50;

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Audit log</h1>
        <label className="text-sm">
          Action{" "}
          <select
            className="rounded border p-1"
            value={action}
            onChange={(e) => {
              setAction(e.target.value as AuditAction | "");
              setPage(1);
            }}
          >
            <option value="">All</option>
            {ACTIONS.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </label>
      </div>
      {isLoading && <p className="text-sm text-gray-500">Loading…</p>}
      {isError && <p className="text-sm text-red-600">{(error as Error).message}</p>}
      {!isLoading && rows.length === 0 && (
        <p className="text-sm text-gray-500">No audit events.</p>
      )}
      {rows.length > 0 && (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-gray-500">
              <th className="py-2">Time</th>
              <th>Actor</th>
              <th>Action</th>
              <th>Run</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((e) => (
              <tr key={e.id} className="border-b align-top">
                <td className="py-2 text-gray-600">{new Date(e.created_at).toLocaleString()}</td>
                <td>{e.actor}</td>
                <td>
                  <span className={`rounded px-1.5 py-0.5 text-xs ${badgeClass[e.action]}`}>
                    {e.action}
                  </span>
                </td>
                <td className="font-mono text-xs">{e.run_id}</td>
                <td className="text-gray-600">
                  {Object.entries(e.detail).map(([k, v]) => (
                    <span key={k} className="mr-2">
                      <span className="text-gray-400">{k}:</span> {String(v)}
                    </span>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="mt-4 flex items-center gap-3 text-sm">
        <button
          disabled={page <= 1}
          onClick={() => setPage((p) => p - 1)}
          className="rounded border px-2 py-1 disabled:opacity-50"
        >
          Prev
        </button>
        <span>Page {page}</span>
        <button
          disabled={page * pageSize >= total}
          onClick={() => setPage((p) => p + 1)}
          className="rounded border px-2 py-1 disabled:opacity-50"
        >
          Next
        </button>
      </div>
    </div>
  );
}
