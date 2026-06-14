import { apiGet, apiGetPage, apiPost } from "./client";
import type { PageMeta } from "./client";

export type MemoryProposalStatus = "proposed" | "applied" | "rejected";

export interface MemoryProposal {
  id: string;
  run_id: string;
  project_id: string;
  branch: string;
  diff: string;
  files: string[];
  status: MemoryProposalStatus;
  pr_url: string | null;
  resolved_at: string | null;
  created_at: string;
}

export const memoryKeys = {
  forRun: (runId: string) => ["memory", runId] as const,
};

export async function getRunMemory(runId: string): Promise<MemoryProposal | null> {
  return apiGet<MemoryProposal | null>(`/runs/${runId}/memory`);
}

export async function applyRunMemory(runId: string): Promise<MemoryProposal> {
  return apiPost<MemoryProposal>(`/runs/${runId}/memory/apply`);
}

export async function rejectRunMemory(runId: string): Promise<MemoryProposal> {
  return apiPost<MemoryProposal>(`/runs/${runId}/memory/reject`);
}

export interface MemoryListParams {
  project_id?: string;
  status?: MemoryProposalStatus;
  page_number?: number;
  page_size?: number;
}

export const memoryListKeys = {
  list: (params: MemoryListParams) => ["memory-proposals", params] as const,
};

export async function listMemoryProposals(
  params: MemoryListParams = {},
): Promise<{ data: MemoryProposal[]; meta?: PageMeta }> {
  const qs = new URLSearchParams();
  if (params.project_id) qs.set("project_id", params.project_id);
  if (params.status) qs.set("status", params.status);
  qs.set("page_number", String(params.page_number ?? 1));
  qs.set("page_size", String(params.page_size ?? 50));
  return apiGetPage<MemoryProposal[]>(`/memory-proposals?${qs.toString()}`);
}
