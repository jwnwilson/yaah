import { useState } from "react";
import { Button } from "../../ui/Button";
import { Input } from "../../ui/Field";
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
            <Button size="sm" onClick={() => approve.mutate()}>Approve</Button>
            <Button size="sm" variant="danger" onClick={() => reject.mutate()}>Reject</Button>
          </>
        )}
        {!isTerminal && (
          <Button size="sm" variant="secondary" onClick={() => cancel.mutate()}>Cancel</Button>
        )}
        <Button size="sm" variant="secondary" onClick={() => setEditing((v) => !v)}>Edit</Button>
      </div>
      {editing && (
        <div className="space-y-1">
          <Input className="text-xs" placeholder="branch" value={branch} onChange={(e) => setBranch(e.target.value)} />
          <Input className="text-xs" placeholder="stage" value={stage} onChange={(e) => setStage(e.target.value)} />
          <Button
            size="sm"
            onClick={() => { edit.mutate({ branch: branch || undefined, stage: stage || undefined }); setEditing(false); }}
          >
            Save fields
          </Button>
        </div>
      )}
      {(cancel.isError || approve.isError || reject.isError || edit.isError) && (
        <p className="text-xs text-danger">Action failed.</p>
      )}
    </div>
  );
}
