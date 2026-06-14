import { apiGet, apiPost } from "./client";

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
