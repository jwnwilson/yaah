import { useQuery } from "@tanstack/react-query";
import { listAllRuns, runKeys } from "@/lib/api/runs";

export function useAllRuns() {
  return useQuery({ queryKey: runKeys.all(), queryFn: listAllRuns });
}
