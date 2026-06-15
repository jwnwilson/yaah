import { apiGet } from "./client";
import type { WorkItem } from "./types";

export interface FeatureProgress {
  feature: WorkItem;
  total: number;
  done: number;
}

export interface EpicBoard {
  epic: WorkItem;
  features: FeatureProgress[];
  tasks: WorkItem[];
  total: number;
  done: number;
}

export const epicKeys = {
  board: (epicId: string) => ["epic-board", epicId] as const,
};

export async function getEpicBoard(
  projectId: string,
  epicId: string,
): Promise<EpicBoard> {
  return apiGet<EpicBoard>(`/projects/${projectId}/epics/${epicId}/board`);
}
