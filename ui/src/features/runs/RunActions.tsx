import { useState } from "react";
import type { Run } from "../../lib/api/types";
import { useRunActions } from "./useRunActions";

const TERMINAL = new Set(["done", "failed", "cancelled"]);

export function RunActions({ taskId, run }: { taskId: string; run: Run }) {
  const { cancel, approve, reject, edit } = useRunActions(taskId, run.id);
  const [editing, setEditing] = useState(false);
  const [branch, setBranch] = useState(run.branch ?? "");
  const [stage, setStage] = useState(run.stage ?? "");

  const isTerminal = TERMINAL.has(run.status);
  const isGate = run.status === "awaiting_approval";

  return (
    <div className="mt-2 space-y-2">
      <div className="flex flex-wrap gap-2">
        {isGate && (
          <>
            <button className="rounded bg-green-600 px-2 py-0.5 text-xs text-white" onClick={() => approve.mutate()}>Approve</button>
            <button className="rounded bg-red-600 px-2 py-0.5 text-xs text-white" onClick={() => reject.mutate()}>Reject</button>
          </>
        )}
        {!isTerminal && (
          <button className="rounded border px-2 py-0.5 text-xs" onClick={() => cancel.mutate()}>Cancel</button>
        )}
        <button className="rounded border px-2 py-0.5 text-xs" onClick={() => setEditing((v) => !v)}>Edit</button>
      </div>
      {editing && (
        <div className="space-y-1">
          <input className="w-full rounded border p-1 text-xs" placeholder="branch" value={branch} onChange={(e) => setBranch(e.target.value)} />
          <input className="w-full rounded border p-1 text-xs" placeholder="stage" value={stage} onChange={(e) => setStage(e.target.value)} />
          <button
            className="rounded bg-blue-600 px-2 py-0.5 text-xs text-white"
            onClick={() => { edit.mutate({ branch: branch || undefined, stage: stage || undefined }); setEditing(false); }}
          >
            Save fields
          </button>
        </div>
      )}
      {(cancel.isError || approve.isError || reject.isError || edit.isError) && (
        <p className="text-xs text-red-600">Action failed.</p>
      )}
    </div>
  );
}
