import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input, Textarea } from "@/components/ui/Field";
import { RunSection } from "@/modules/runs/RunSection";
import { AcceptanceCriteria } from "./AcceptanceCriteria";
import { Attachments } from "./Attachments";
import { useUpdateWorkItem } from "./useUpdateWorkItem";
import { useWorkItem } from "./useWorkItem";

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
    <aside className="fixed right-0 top-0 h-screen w-[28rem] overflow-y-auto border-l border-line bg-surface p-4 shadow-xl">
      <div className="mb-3 flex justify-between">
        <h2 className="font-semibold text-fg">Ticket</h2>
        <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
      </div>
      {isLoading && <p className="text-sm text-subtle">Loading…</p>}
      {isError && <p className="text-sm text-danger">{(error as Error).message}</p>}
      {data && (
        <div className="space-y-4">
          <Input className="font-medium" value={title} onChange={(e) => setTitle(e.target.value)} />
          <Textarea className="h-28" value={body} onChange={(e) => setBody(e.target.value)} />
          <div>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-subtle">Acceptance criteria</h3>
            <AcceptanceCriteria value={criteria} onChange={setCriteria} />
          </div>
          <Attachments itemId={itemId} />
          {update.isError && <p className="text-sm text-danger">{(update.error as Error).message}</p>}
          <Button size="sm" loading={update.isPending} onClick={() => update.mutate({ title, body, acceptance_criteria: criteria })}>Save</Button>
          <RunSection projectId={projectId} taskId={itemId} taskStatus={data.status} />
        </div>
      )}
    </aside>
  );
}
