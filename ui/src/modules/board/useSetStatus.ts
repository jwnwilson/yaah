import { useMutation, useQueryClient } from "@tanstack/react-query";
import { backlogKeys } from "@/lib/api/backlog";
import type { WorkItem, WorkItemStatus } from "@/lib/api/types";
import { setWorkItemStatus, workItemKeys } from "@/lib/api/workItems";

interface Vars {
  itemId: string;
  status: WorkItemStatus;
}

export function useSetStatus(projectId: string) {
  const qc = useQueryClient();
  const key = workItemKeys.list(projectId);
  return useMutation({
    mutationFn: ({ itemId, status }: Vars) => setWorkItemStatus(itemId, status),
    onMutate: async ({ itemId, status }) => {
      await qc.cancelQueries({ queryKey: key });
      const previous = qc.getQueryData<WorkItem[]>(key);
      qc.setQueryData<WorkItem[]>(key, (old) =>
        (old ?? []).map((i) => (i.id === itemId ? { ...i, status } : i)),
      );
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) qc.setQueryData(key, ctx.previous);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: key });
      qc.invalidateQueries({ queryKey: backlogKeys.view(projectId) });
    },
  });
}
