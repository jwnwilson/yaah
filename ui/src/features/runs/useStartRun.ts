import { useMutation, useQueryClient } from "@tanstack/react-query";
import { runKeys, startRun } from "../../lib/api/runs";

export function useStartRun(projectId: string, taskId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => startRun(taskId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: runKeys.forTask(taskId) });
      qc.invalidateQueries({ queryKey: ["work-items", projectId] }); // start moves task to in_progress
    },
  });
}
