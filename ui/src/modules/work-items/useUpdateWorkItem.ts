import { useMutation, useQueryClient } from "@tanstack/react-query";
import { workItemDetailKey } from "@/lib/api/workItemDetail";
import { updateWorkItem, workItemKeys, type UpdateWorkItemInput } from "@/lib/api/workItems";

export function useUpdateWorkItem(projectId: string, itemId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: UpdateWorkItemInput) => updateWorkItem(itemId, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: workItemDetailKey(itemId) });
      qc.invalidateQueries({ queryKey: workItemKeys.list(projectId) });
    },
  });
}
