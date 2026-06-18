import { apiGet, apiPost } from "./client";
import type { WorkItem } from "./types";

export interface BacklogEpic {
  epic: WorkItem;
  active: boolean;
  ready_count: number;
  total_tasks: number;
  done: number;
  in_flight_count: number;
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

export async function activateEpic(projectId: string, epicId: string): Promise<WorkItem> {
  return apiPost<WorkItem>(`/projects/${projectId}/epics/${epicId}/activate`);
}

export async function deactivateEpic(projectId: string, epicId: string): Promise<WorkItem> {
  return apiPost<WorkItem>(`/projects/${projectId}/epics/${epicId}/deactivate`);
}
