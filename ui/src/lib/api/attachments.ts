import { BASE, apiDelete, apiGet, apiPostForm } from "./client";

export interface WorkItemAttachment {
  id: string;
  work_item_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  origin: string;
  created_at: string;
}

export const attachmentKeys = {
  forItem: (itemId: string) => ["attachments", itemId] as const,
};

export function attachmentUrl(attachmentId: string): string {
  return `${BASE}/attachments/${attachmentId}`;
}

export function isImage(att: WorkItemAttachment): boolean {
  return att.content_type.startsWith("image/");
}

export async function getAttachments(itemId: string): Promise<WorkItemAttachment[]> {
  return apiGet<WorkItemAttachment[]>(`/work-items/${itemId}/attachments`);
}

export async function uploadAttachment(itemId: string, file: File): Promise<WorkItemAttachment> {
  const form = new FormData();
  form.append("file", file);
  return apiPostForm<WorkItemAttachment>(`/work-items/${itemId}/attachments`, form);
}

export async function deleteAttachment(attachmentId: string): Promise<void> {
  await apiDelete(`/attachments/${attachmentId}`);
}
