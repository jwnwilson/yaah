import { useMemoryProposal } from "./useMemoryProposal";
import { MemoryDiff } from "./MemoryDiff";

export function MemoryProposalCard({ runId }: { runId: string }) {
  const { query, apply, reject } = useMemoryProposal(runId);
  const proposal = query.data;

  if (query.isLoading || !proposal) return null;

  const isProposed = proposal.status === "proposed";

  return (
    <div className="mt-2 rounded border border-amber-300 bg-amber-50 p-2 text-xs">
      <div className="flex items-center justify-between">
        <span className="font-semibold text-amber-800">
          Memory proposal · {proposal.files.length} file(s)
        </span>
        <span className="rounded bg-amber-200 px-1.5 py-0.5 text-amber-900">
          {proposal.status}
        </span>
      </div>
      <ul className="mt-1 list-disc pl-4 text-gray-700">
        {proposal.files.map((f) => (
          <li key={f}>{f}</li>
        ))}
      </ul>
      <MemoryDiff diff={proposal.diff} />
      {isProposed && (
        <div className="mt-2 flex gap-2">
          <button
            className="rounded bg-green-600 px-2 py-0.5 text-white"
            onClick={() => apply.mutate()}
            disabled={apply.isPending}
          >
            Apply
          </button>
          <button
            className="rounded bg-red-600 px-2 py-0.5 text-white"
            onClick={() => reject.mutate()}
            disabled={reject.isPending}
          >
            Reject
          </button>
        </div>
      )}
      {proposal.pr_url && (
        <a className="mt-1 block text-blue-700 underline" href={proposal.pr_url}>
          View PR
        </a>
      )}
      {(apply.isError || reject.isError) && (
        <p className="mt-1 text-red-600">Action failed.</p>
      )}
    </div>
  );
}
