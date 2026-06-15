import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  applyRunMemory,
  getRunMemory,
  memoryKeys,
  rejectRunMemory,
} from "@/lib/api/memory";

export function useMemoryProposal(runId: string) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: memoryKeys.forRun(runId) });

  const query = useQuery({
    queryKey: memoryKeys.forRun(runId),
    queryFn: () => getRunMemory(runId),
  });
  const apply = useMutation({ mutationFn: () => applyRunMemory(runId), onSuccess: invalidate });
  const reject = useMutation({ mutationFn: () => rejectRunMemory(runId), onSuccess: invalidate });

  return { query, apply, reject };
}
