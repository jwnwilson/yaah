import { useState } from "react";
import { Button } from "../../ui/Button";
import { useMemoryProposal } from "./useMemoryProposal";

export function MemoryProposalCard({ runId }: { runId: string }) {
  const { query, apply, reject } = useMemoryProposal(runId);
  const [open, setOpen] = useState(false);
  const proposal = query.data;

  if (query.isLoading || !proposal) return null;

  const isProposed = proposal.status === "proposed";

  return (
    <div className="mt-2 rounded-md border border-warning/40 bg-warning-subtle p-2 text-xs">
      <div className="flex items-center justify-between">
        <span className="font-semibold text-warning">Memory proposal · {proposal.files.length} file(s)</span>
        <span className="rounded-full bg-warning/20 px-1.5 py-0.5 text-warning">{proposal.status}</span>
      </div>
      <ul className="mt-1 list-disc pl-4 text-muted">
        {proposal.files.map((f) => (
          <li key={f}>{f}</li>
        ))}
      </ul>
      <button className="mt-1 text-accent hover:underline" onClick={() => setOpen((v) => !v)}>
        {open ? "Hide diff" : "Show diff"}
      </button>
      {open && (
        <pre className="mt-1 max-h-64 overflow-auto rounded bg-surface p-2 text-[11px] text-fg">{proposal.diff}</pre>
      )}
      {isProposed && (
        <div className="mt-2 flex gap-2">
          <Button size="sm" onClick={() => apply.mutate()} loading={apply.isPending}>Apply</Button>
          <Button size="sm" variant="danger" onClick={() => reject.mutate()} loading={reject.isPending}>Reject</Button>
        </div>
      )}
      {proposal.pr_url && (
        <a className="mt-1 block text-accent hover:underline" href={proposal.pr_url}>View PR</a>
      )}
      {(apply.isError || reject.isError) && <p className="mt-1 text-danger">Action failed.</p>}
    </div>
  );
}
