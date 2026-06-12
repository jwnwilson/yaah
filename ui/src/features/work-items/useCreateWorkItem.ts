import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createWorkItem, workItemKeys, type CreateWorkItemInput } from "../../lib/api/workItems";

export function useCreateWorkItem(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateWorkItemInput) => createWorkItem(projectId, input),
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["hierarchy", projectId, created.kind] });
      qc.invalidateQueries({ queryKey: workItemKeys.list(projectId) });
    },
  });
}
