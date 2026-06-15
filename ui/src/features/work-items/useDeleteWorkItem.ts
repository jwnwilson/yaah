import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteWorkItem, workItemKeys } from "@/lib/api/workItems";

export function useDeleteWorkItem(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (itemId: string) => deleteWorkItem(itemId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["hierarchy", projectId] });
      qc.invalidateQueries({ queryKey: workItemKeys.list(projectId) });
    },
  });
}
