import { apiGetPage, apiPatch, apiPost } from "./client";
import type { Run } from "./types";

export const runKeys = {
  forTask: (taskId: string) => ["runs", taskId] as const,
};

export async function listRuns(taskId: string): Promise<Run[]> {
  const { data } = await apiGetPage<Run[]>(`/work-items/${taskId}/runs?page_size=100`);
  return data;
}

export async function startRun(taskId: string): Promise<Run> {
  return apiPost<Run>(`/work-items/${taskId}/runs`);
}

export async function cancelRun(runId: string): Promise<Run> {
  return apiPost<Run>(`/runs/${runId}/cancel`);
}

export async function approveRun(runId: string): Promise<Run> {
  return apiPost<Run>(`/runs/${runId}/approve`);
}

export async function rejectRun(runId: string): Promise<Run> {
  return apiPost<Run>(`/runs/${runId}/reject`);
}

export interface UpdateRunInput {
  stage?: string;
  branch?: string;
  pr_url?: string;
}

export async function updateRun(runId: string, input: UpdateRunInput): Promise<Run> {
  return apiPatch<Run>(`/runs/${runId}`, input);
}
