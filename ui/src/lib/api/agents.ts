import { apiGetPage, apiPatch } from "./client";

export interface Agent {
  id: string;
  team_id: string;
  role: string;
  name: string;
  persona: string;
  model_alias: string;
  runtime: string;
  purpose: string;
  system_prompt: string;
  allowed_tools: string[];
  skill_ids: string[];
  mcp_server_ids: string[];
  secret_ids: string[];
}

export interface UpdateAgentInput {
  name?: string;
  model_alias?: string;
  allowed_tools?: string[];
  skill_ids?: string[];
  mcp_server_ids?: string[];
  secret_ids?: string[];
}

export const agentKeys = {
  forTeam: (teamId: string) => ["agents", teamId] as const,
};

export async function listAgents(teamId: string): Promise<Agent[]> {
  return (await apiGetPage<Agent[]>(`/teams/${teamId}/agents?page_size=200`)).data;
}

export async function updateAgent(id: string, input: UpdateAgentInput): Promise<Agent> {
  return apiPatch<Agent>(`/agents/${id}`, input);
}
