import { apiGet, apiGetPage } from "./client";

export type NotificationCategory = "review" | "run" | "system";
export type NotificationSeverity = "info" | "attention";

export interface NotificationAction {
  kind: "gate_approval";
  run_id: string;
}

export interface Notification {
  id: string;
  category: NotificationCategory;
  severity: NotificationSeverity;
  title: string;
  body: string | null;
  run_id: string | null;
  action: NotificationAction | null;
  read_at: string | null;
  resolved_at: string | null;
}

export const notificationKeys = {
  unreadCount: ["notifications", "unread-count"] as const,
  list: ["notifications", "list"] as const,
};

export async function getUnreadCount(): Promise<number> {
  const data = await apiGet<{ count: number }>("/notifications/unread-count");
  return data.count;
}

export async function listNotifications(): Promise<Notification[]> {
  const { data } = await apiGetPage<Notification[]>("/notifications?page_size=50");
  return data;
}
