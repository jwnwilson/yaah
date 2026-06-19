import { useState } from "react";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";
import type { AuditAction } from "@/lib/api/audit";
import { useAudit } from "./useAudit";

const ACTIONS: AuditAction[] = ["capability_granted", "tool_allowed", "tool_denied"];

const actionTone: Record<AuditAction, BadgeTone> = {
  capability_granted: "info",
  tool_allowed: "success",
  tool_denied: "danger",
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
    <div className="flex h-full flex-col">
      <PageHeader title="Audit log" />
      <div className="flex-1 overflow-auto p-6">
      <div className="mb-4 flex items-center justify-end">
        <label className="text-sm">
          Action{" "}
          <select
            className="rounded-md border border-line bg-surface px-2 py-1 text-sm text-fg"
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
      {isLoading && <p className="text-sm text-subtle">Loading…</p>}
      {isError && <p className="text-sm text-danger">{(error as Error).message}</p>}
      {!isLoading && rows.length === 0 && (
        <p className="text-sm text-subtle">No audit events.</p>
      )}
      {rows.length > 0 && (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-subtle">
              <th className="py-2">Time</th>
              <th>Actor</th>
              <th>Action</th>
              <th>Run</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((e) => (
              <tr key={e.id} className="border-b border-line align-top">
                <td className="py-2 text-muted">{new Date(e.created_at).toLocaleString()}</td>
                <td>{e.actor}</td>
                <td>
                  <Badge tone={actionTone[e.action]}>{e.action}</Badge>
                </td>
                <td className="font-mono text-xs">{e.run_id}</td>
                <td className="text-muted">
                  {Object.entries(e.detail).map(([k, v]) => (
                    <span key={k} className="mr-2">
                      <span className="text-subtle">{k}:</span> {String(v)}
                    </span>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="mt-4 flex items-center gap-3 text-sm">
        <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
          Prev
        </Button>
        <span>Page {page}</span>
        <Button size="sm" variant="secondary" disabled={page * pageSize >= total} onClick={() => setPage((p) => p + 1)}>
          Next
        </Button>
      </div>
      </div>
    </div>
  );
}
