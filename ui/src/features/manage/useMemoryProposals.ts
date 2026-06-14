import { useQuery } from "@tanstack/react-query";
import { listMemoryProposals, memoryListKeys, type MemoryListParams } from "../../lib/api/memory";

export function useMemoryProposals(params: MemoryListParams) {
  return useQuery({ queryKey: memoryListKeys.list(params), queryFn: () => listMemoryProposals(params) });
}
