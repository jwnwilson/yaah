import { useMutation, useQueryClient } from "@tanstack/react-query";
import { runKeys, startRun } from "@/lib/api/runs";
import { workItemKeys } from "@/lib/api/workItems";

export function useStartRun(projectId: string, taskId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => startRun(taskId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: runKeys.forTask(taskId) });
      qc.invalidateQueries({ queryKey: workItemKeys.list(projectId) }); // start moves task to in_progress
    },
  });
}
