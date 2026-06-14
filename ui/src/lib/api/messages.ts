import { apiGet, apiGetPage, apiPatch, apiPost } from "./client";

export type MessageKind = "dispatch" | "report" | "chat" | "status";

export interface Message {
  id: string;
  sender_kind: "agent" | "system" | "user";
  sender_agent_id: string | null;
  recipient_kind: "agent" | "user";
  recipient_agent_id: string | null;
  kind: MessageKind;
  subject: string;
  body: string;
  run_id: string | null;
  work_item_id: string | null;
  project_id: string | null;
  read_at: string | null;
  created_at: string;
}

export interface SendMessageInput {
  recipient_kind: "agent" | "user";
  recipient_agent_id?: string | null;
  kind?: MessageKind;
  subject?: string;
  body: string;
}

export const messageKeys = {
  list: (box: string) => ["messages", "list", box] as const,
  unread: (box: string) => ["messages", "unread", box] as const,
  sent: (agentId: string) => ["messages", "sent", agentId] as const,
};

export async function listMessages(box: string): Promise<Message[]> {
  const q = encodeURIComponent(box);
  return (await apiGetPage<Message[]>(`/messages?box=${q}&page_size=100`)).data;
}

export async function listSentMessages(agentId: string): Promise<Message[]> {
  const q = encodeURIComponent(agentId);
  return (await apiGetPage<Message[]>(`/messages?sender=${q}&page_size=100`)).data;
}

export async function getMessageUnreadCount(box: string): Promise<number> {
  const q = encodeURIComponent(box);
  return (await apiGet<{ count: number }>(`/messages/unread-count?box=${q}`)).count;
}

export async function markMessageRead(id: string): Promise<Message> {
  return apiPatch<Message>(`/messages/${id}`, { read: true });
}

export async function sendMessage(input: SendMessageInput): Promise<Message> {
  return apiPost<Message>("/messages", input);
}
