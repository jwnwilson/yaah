import { apiDelete, apiGetPage, apiPatch, apiPost, apiPut } from "./client";
import type { McpServer, McpTransport, Secret, Skill } from "./types";

// ---- Secrets (write-only values) ----
export const secretKeys = { all: ["secrets"] as const };

export interface CreateSecretInput { name: string; description?: string }
export interface UpdateSecretInput { name?: string; description?: string }

export async function listSecrets(): Promise<Secret[]> {
  return (await apiGetPage<Secret[]>("/secrets?page_size=200")).data;
}
export async function createSecret(input: CreateSecretInput): Promise<Secret> {
  return apiPost<Secret>("/secrets", input);
}
export async function updateSecret(id: string, input: UpdateSecretInput): Promise<Secret> {
  return apiPatch<Secret>(`/secrets/${id}`, input);
}
export async function setSecretValue(id: string, value: string): Promise<Secret> {
  return apiPut<Secret>(`/secrets/${id}/value`, { value });
}
export async function deleteSecret(id: string): Promise<{ deleted: string }> {
  return apiDelete<{ deleted: string }>(`/secrets/${id}`);
}

// ---- Skills ----
export const skillKeys = { all: ["skills"] as const };

export interface CreateSkillInput { name: string; description?: string; source?: string }
export interface UpdateSkillInput { name?: string; description?: string; source?: string }

export async function listSkills(): Promise<Skill[]> {
  return (await apiGetPage<Skill[]>("/skills?page_size=200")).data;
}
export async function createSkill(input: CreateSkillInput): Promise<Skill> {
  return apiPost<Skill>("/skills", input);
}
export async function updateSkill(id: string, input: UpdateSkillInput): Promise<Skill> {
  return apiPatch<Skill>(`/skills/${id}`, input);
}
export async function deleteSkill(id: string): Promise<{ deleted: string }> {
  return apiDelete<{ deleted: string }>(`/skills/${id}`);
}

// ---- MCP servers ----
export const mcpServerKeys = { all: ["mcp-servers"] as const };

export interface CreateMcpServerInput { name: string; transport: McpTransport; command_or_url: string; tool_allowlist: string[] }
export interface UpdateMcpServerInput { name?: string; transport?: McpTransport; command_or_url?: string; tool_allowlist?: string[] }

export async function listMcpServers(): Promise<McpServer[]> {
  return (await apiGetPage<McpServer[]>("/mcp-servers?page_size=200")).data;
}
export async function createMcpServer(input: CreateMcpServerInput): Promise<McpServer> {
  return apiPost<McpServer>("/mcp-servers", input);
}
export async function updateMcpServer(id: string, input: UpdateMcpServerInput): Promise<McpServer> {
  return apiPatch<McpServer>(`/mcp-servers/${id}`, input);
}
export async function deleteMcpServer(id: string): Promise<{ deleted: string }> {
  return apiDelete<{ deleted: string }>(`/mcp-servers/${id}`);
}
