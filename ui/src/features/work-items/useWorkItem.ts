import { useQuery } from "@tanstack/react-query";
import { getWorkItem, workItemDetailKey } from "../../lib/api/workItemDetail";

export function useWorkItem(itemId: string) {
  return useQuery({ queryKey: workItemDetailKey(itemId), queryFn: () => getWorkItem(itemId) });
}
