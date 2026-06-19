import { apiGet, apiPost } from "./client";
import type { WorkItem } from "./types";

export interface BacklogFeature {
  feature: WorkItem;
  tasks: WorkItem[];
}

export interface BacklogEpic {
  epic: WorkItem;
  active: boolean;
  ready_count: number;
  total_tasks: number;
  done: number;
  in_flight_count: number;
  features: BacklogFeature[];
  tasks: WorkItem[];
}

export interface BacklogView {
  epics: BacklogEpic[];
  max_concurrent_runs: number;
  in_flight: number;
  queued: number;
}

export const backlogKeys = {
  view: (projectId: string) => ["backlog", projectId] as const,
};

export async function getBacklog(projectId: string): Promise<BacklogView> {
  return apiGet<BacklogView>(`/projects/${projectId}/backlog`);
}

/** Activate an epic or feature (move it onto the board; auto-starts its ready tasks). */
export async function activateItem(projectId: string, itemId: string): Promise<WorkItem> {
  return apiPost<WorkItem>(`/projects/${projectId}/work-items/${itemId}/activate`);
}

/** Deactivate an epic or feature (move it back to the backlog). */
export async function deactivateItem(projectId: string, itemId: string): Promise<WorkItem> {
  return apiPost<WorkItem>(`/projects/${projectId}/work-items/${itemId}/deactivate`);
}

export async function reorderWorkItems(
  projectId: string,
  parentId: string | null,
  orderedIds: string[],
): Promise<void> {
  await apiPost(`/projects/${projectId}/work-items/reorder`, {
    parent_id: parentId,
    ordered_ids: orderedIds,
  });
}
