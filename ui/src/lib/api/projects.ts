import { apiGetPage, apiPatch, apiPost } from "./client";
import type { Project } from "./types";

export const projectKeys = {
  all: ["projects"] as const,
};

export interface CreateProjectInput {
  name: string;
  repo_url?: string;
  local_path?: string;
}

export async function listProjects(): Promise<Project[]> {
  const { data } = await apiGetPage<Project[]>("/projects?page_size=200");
  return data;
}

export async function createProject(input: CreateProjectInput): Promise<Project> {
  return apiPost<Project>("/projects", input);
}

export async function updateProject(
  projectId: string,
  input: { max_concurrent_runs?: number; team_id?: string; name?: string },
): Promise<Project> {
  return apiPatch<Project>(`/projects/${projectId}`, input);
}
