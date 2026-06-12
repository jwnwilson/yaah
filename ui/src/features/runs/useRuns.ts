import { useQuery } from "@tanstack/react-query";
import { listRuns, runKeys } from "../../lib/api/runs";

export function useRuns(taskId: string) {
  return useQuery({ queryKey: runKeys.forTask(taskId), queryFn: () => listRuns(taskId) });
}
