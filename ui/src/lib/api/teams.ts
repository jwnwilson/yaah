import { apiGetPage } from "./client";

export interface Team {
  id: string;
  owner_id: string;
  name: string;
  created_at: string;
}

export const teamKeys = { all: ["teams"] as const };

export async function listTeams(): Promise<Team[]> {
  return (await apiGetPage<Team[]>("/teams")).data;
}
