import { useQuery } from "@tanstack/react-query";
import type { WorkItem } from "@/lib/api/types";
import { listWorkItems } from "@/lib/api/workItems";

export function useEpics(projectId: string) {
  return useQuery<WorkItem[]>({
    queryKey: ["hierarchy", projectId, "epic"],
    queryFn: () => listWorkItems(projectId, { kind: "epic" }),
  });
}

export function useFeatures(projectId: string) {
  return useQuery<WorkItem[]>({
    queryKey: ["hierarchy", projectId, "feature"],
    queryFn: () => listWorkItems(projectId, { kind: "feature" }),
  });
}
