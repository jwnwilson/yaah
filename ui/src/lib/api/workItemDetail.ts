import { apiGet } from "./client";
import type { WorkItem } from "./types";

export const workItemDetailKey = (id: string) => ["work-item", id] as const;

export async function getWorkItem(itemId: string): Promise<WorkItem> {
  return apiGet<WorkItem>(`/work-items/${itemId}`);
}
