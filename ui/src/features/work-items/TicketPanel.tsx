import { useEffect, useState } from "react";
import { useWorkItem } from "./useWorkItem";
import { useUpdateWorkItem } from "./useUpdateWorkItem";
import { AcceptanceCriteria } from "./AcceptanceCriteria";
import { RunSection } from "../runs/RunSection";

export function TicketPanel({
  projectId,
  itemId,
  onClose,
}: {
  projectId: string;
  itemId: string;
  onClose: () => void;
}) {
  const { data, isLoading, isError, error } = useWorkItem(itemId);
  const update = useUpdateWorkItem(projectId, itemId);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [criteria, setCriteria] = useState<string[]>([]);

  useEffect(() => {
    if (data) {
      setTitle(data.title);
      setBody(data.body);
      setCriteria(data.acceptance_criteria);
    }
  }, [data]);

  return (
    <aside className="fixed right-0 top-0 h-screen w-[28rem] overflow-y-auto border-l bg-white p-4 shadow-xl">
      <div className="mb-3 flex justify-between">
        <h2 className="font-semibold">Ticket</h2>
        <button onClick={onClose} className="text-sm text-gray-500">Close</button>
      </div>
      {isLoading && <p className="text-sm text-gray-500">Loading…</p>}
      {isError && <p className="text-sm text-red-600">{(error as Error).message}</p>}
      {data && (
        <div className="space-y-4">
          <input className="w-full rounded border p-2 text-sm font-medium" value={title} onChange={(e) => setTitle(e.target.value)} />
          <textarea className="h-28 w-full rounded border p-2 text-sm" value={body} onChange={(e) => setBody(e.target.value)} />
          <div>
            <h3 className="mb-1 text-xs font-semibold uppercase text-gray-500">Acceptance criteria</h3>
            <AcceptanceCriteria value={criteria} onChange={setCriteria} />
          </div>
          {update.isError && <p className="text-sm text-red-600">{(update.error as Error).message}</p>}
          <button
            className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50"
            disabled={update.isPending}
            onClick={() => update.mutate({ title, body, acceptance_criteria: criteria })}
          >
            Save
          </button>
          <RunSection projectId={projectId} taskId={itemId} taskStatus={data.status} />
        </div>
      )}
    </aside>
  );
}
