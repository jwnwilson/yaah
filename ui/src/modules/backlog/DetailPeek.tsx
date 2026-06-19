import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input, Textarea } from "@/components/ui/Field";
import { IconButton } from "@/components/ui/IconButton";
import { backlogKeys } from "@/lib/api/backlog";
import type { WorkItemStatus } from "@/lib/api/types";
import { workItemDetailKey } from "@/lib/api/workItemDetail";
import { setWorkItemStatus, updateWorkItem } from "@/lib/api/workItems";
import { RunSection } from "@/modules/runs/RunSection";
import { useRuns } from "@/modules/runs/useRuns";
import { AcceptanceCriteria } from "@/modules/work-items/AcceptanceCriteria";
import { Attachments } from "@/modules/work-items/Attachments";
import { useWorkItem } from "@/modules/work-items/useWorkItem";
import { StatusPill } from "./StatusPill";

/** Linear-style side peek for a single work item. Reuses the shared acceptance-criteria,
 * attachments, and run editors inside a restyled shell. */
export function DetailPeek({
  projectId,
  itemId,
  onClose,
}: {
  projectId: string;
  itemId: string;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const { data, isLoading, isError, error } = useWorkItem(itemId);
  const { data: runs } = useRuns(itemId);
  const latestRun = runs?.[0];

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

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: workItemDetailKey(itemId) });
    qc.invalidateQueries({ queryKey: backlogKeys.view(projectId) });
  };

  const save = useMutation({
    mutationFn: () => updateWorkItem(itemId, { title, body, acceptance_criteria: criteria }),
    onSuccess: invalidate,
  });

  const changeStatus = useMutation({
    mutationFn: (status: WorkItemStatus) => setWorkItemStatus(itemId, status),
    onSuccess: invalidate,
  });

  return (
    <aside className="fixed right-0 top-0 z-20 flex h-screen w-[30rem] flex-col overflow-y-auto border-l border-line bg-surface shadow-xl">
      <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-3">
        <span className="text-xs uppercase tracking-wide text-subtle">{data?.kind ?? "item"}</span>
        <div className="flex items-center gap-2">
          {latestRun && (
            <Link
              to={`/runs/${latestRun.id}`}
              className="rounded-md bg-accent px-3 py-1 text-sm font-medium text-white hover:opacity-90"
            >
              View run →
            </Link>
          )}
          <IconButton label="close" onClick={onClose}>✕</IconButton>
        </div>
      </div>

      {isLoading && <p className="p-4 text-sm text-subtle">Loading…</p>}
      {isError && <p className="p-4 text-sm text-danger">{(error as Error).message}</p>}
      {data && (
        <div className="space-y-4 p-4">
          <Input
            className="text-base font-medium"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <div className="flex items-center gap-2">
            <span className="text-xs text-subtle">Status</span>
            <StatusPill status={data.status} onChange={(s) => changeStatus.mutate(s)} />
          </div>
          <div>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-subtle">
              Description
            </h3>
            <Textarea className="h-28" value={body} onChange={(e) => setBody(e.target.value)} />
          </div>
          <div>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-subtle">
              Acceptance criteria
            </h3>
            <AcceptanceCriteria value={criteria} onChange={setCriteria} />
          </div>
          <Attachments itemId={itemId} />
          {save.isError && <p className="text-sm text-danger">{(save.error as Error).message}</p>}
          <Button size="sm" loading={save.isPending} onClick={() => save.mutate()}>
            Save
          </Button>
          {data.kind === "task" && (
            <RunSection projectId={projectId} taskId={itemId} taskStatus={data.status} />
          )}
        </div>
      )}
    </aside>
  );
}
