import { useQuery } from "@tanstack/react-query";
import { listWorkItems, workItemKeys, type WorkItemFilters } from "../../lib/api/workItems";

export function useBoardItems(projectId: string, parentId?: string) {
  const filters: WorkItemFilters = { kind: "task", parent_id: parentId };
  return useQuery({
    queryKey: parentId
      ? [...workItemKeys.list(projectId), "feature", parentId]
      : workItemKeys.list(projectId),
    queryFn: () => listWorkItems(projectId, filters),
  });
}
