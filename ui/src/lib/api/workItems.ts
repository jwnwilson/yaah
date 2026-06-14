import { apiDelete, apiGetPage, apiPatch, apiPost } from "./client";
import type { WorkItem, WorkItemKind, WorkItemStatus } from "./types";

export const workItemKeys = {
  list: (projectId: string) => ["work-items", projectId] as const,
};

export interface WorkItemFilters {
  kind?: WorkItemKind;
  parent_id?: string;
}

export async function listWorkItems(
  projectId: string,
  filters: WorkItemFilters = {},
): Promise<WorkItem[]> {
  const params = new URLSearchParams({ page_size: "200" });
  if (filters.kind) params.set("kind", filters.kind);
  if (filters.parent_id) params.set("parent_id", filters.parent_id);
  const { data } = await apiGetPage<WorkItem[]>(`/projects/${projectId}/work-items?${params}`);
  return data;
}

export interface CreateWorkItemInput {
  kind: WorkItemKind;
  title: string;
  body?: string;
  parent_id?: string;
  acceptance_criteria?: string[];
}

export async function createWorkItem(projectId: string, input: CreateWorkItemInput): Promise<WorkItem> {
  return apiPost<WorkItem>(`/projects/${projectId}/work-items`, input);
}

export interface UpdateWorkItemInput {
  title?: string;
  body?: string;
  acceptance_criteria?: string[];
  assignee_agent_id?: string | null;
}

export async function updateWorkItem(itemId: string, input: UpdateWorkItemInput): Promise<WorkItem> {
  return apiPatch<WorkItem>(`/work-items/${itemId}`, input);
}

export async function setWorkItemStatus(itemId: string, status: WorkItemStatus): Promise<WorkItem> {
  return apiPost<WorkItem>(`/work-items/${itemId}/status`, { status });
}

export async function deleteWorkItem(itemId: string): Promise<void> {
  await apiDelete(`/work-items/${itemId}`);
}
