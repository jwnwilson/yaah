import { apiGet, apiGetPage, apiPatch, apiPost } from "./client";
import type { AuditEvent, Run, RunEvent, RunUsage } from "./types";

export const runKeys = {
  forTask: (taskId: string) => ["runs", taskId] as const,
  detail: (runId: string) => ["runs", "detail", runId] as const,
  events: (runId: string) => ["runs", "events", runId] as const,
  usage: (runId: string) => ["runs", "usage", runId] as const,
  audit: (runId: string) => ["runs", "audit", runId] as const,
};

export async function listRuns(taskId: string): Promise<Run[]> {
  const { data } = await apiGetPage<Run[]>(`/work-items/${taskId}/runs?page_size=100`);
  return data;
}

export async function getRun(runId: string): Promise<Run> {
  return apiGet<Run>(`/runs/${runId}`);
}

export async function listRunEvents(runId: string): Promise<RunEvent[]> {
  const { data } = await apiGetPage<RunEvent[]>(`/runs/${runId}/events?page_size=200`);
  return data;
}

export async function getRunUsage(runId: string): Promise<RunUsage> {
  return apiGet<RunUsage>(`/runs/${runId}/usage`);
}

export async function listRunAudit(runId: string): Promise<AuditEvent[]> {
  const { data } = await apiGetPage<AuditEvent[]>(`/runs/${runId}/audit?page_size=200`);
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
