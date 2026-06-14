import { apiGet } from "./client";

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_creation_tokens: number;
  cost_usd: number;
  total_tokens: number;
}

export type UsageGroupBy = "stage" | "agent_role" | "model";

export interface UsageRollup {
  totals: TokenUsage;
  group_by?: UsageGroupBy;
  groups?: Record<string, TokenUsage>;
}

export interface UsageParams {
  group_by?: UsageGroupBy;
  project_id?: string;
  since?: string;
  until?: string;
}

export const usageKeys = {
  rollup: (params: UsageParams) => ["usage", params] as const,
};

export async function getUsage(params: UsageParams = {}): Promise<UsageRollup> {
  const qs = new URLSearchParams();
  if (params.group_by) qs.set("group_by", params.group_by);
  if (params.project_id) qs.set("project_id", params.project_id);
  if (params.since) qs.set("since", params.since);
  if (params.until) qs.set("until", params.until);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return apiGet<UsageRollup>(`/usage${suffix}`);
}
