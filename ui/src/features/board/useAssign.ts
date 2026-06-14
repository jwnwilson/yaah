import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateWorkItem, workItemKeys } from "../../lib/api/workItems";
import type { WorkItem } from "../../lib/api/types";

interface Vars {
  itemId: string;
  assigneeAgentId: string | null;
}

export function useAssign(projectId: string) {
  const qc = useQueryClient();
  const key = workItemKeys.list(projectId);
  return useMutation({
    mutationFn: ({ itemId, assigneeAgentId }: Vars) =>
      updateWorkItem(itemId, { assignee_agent_id: assigneeAgentId }),
    onMutate: async ({ itemId, assigneeAgentId }) => {
      await qc.cancelQueries({ queryKey: key });
      const previous = qc.getQueryData<WorkItem[]>(key);
      qc.setQueryData<WorkItem[]>(key, (old) =>
        (old ?? []).map((i) =>
          i.id === itemId ? { ...i, assignee_agent_id: assigneeAgentId } : i,
        ),
      );
      return { previous };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.previous) qc.setQueryData(key, ctx.previous);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });
}
