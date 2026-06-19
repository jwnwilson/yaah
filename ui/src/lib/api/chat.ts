import type { ThreadMessage, ThreadParticipant } from "@/components/ui/chat/types";
import { apiGetPage, apiPost } from "./client";

export interface EpicSpecEdit {
  body?: string | null;
  acceptance_criteria?: string[] | null;
}

export interface ProposedUpdate {
  id: string;
  kind: string;
  current_title: string;
  title?: string | null;
  body?: string | null;
  acceptance_criteria?: string[] | null;
}

export interface ChatTurn {
  session_id: string;
  reply: string;
  created_items: unknown[];
  proposed_epic_update?: EpicSpecEdit | null;
  proposed_updates?: ProposedUpdate[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
}

export const chatKeys = {
  messages: (sid: string) => ["chat", sid] as const,
};

export async function postChat(
  projectId: string,
  message: string,
  sessionId?: string,
  epicId?: string,
): Promise<ChatTurn> {
  return apiPost<ChatTurn>(`/projects/${projectId}/chat`, {
    message,
    session_id: sessionId,
    epic_id: epicId,
  });
}

export async function listMessages(sessionId: string): Promise<ChatMessage[]> {
  const { data } = await apiGetPage<ChatMessage[]>(
    `/chat/${sessionId}/messages?page_size=200`,
  );
  return data;
}

export interface ChatSession {
  id: string;
  project_id: string;
  epic_id?: string | null;
  created_at: string;
}

export async function listSessions(projectId: string): Promise<ChatSession[]> {
  const { data } = await apiGetPage<ChatSession[]>(`/projects/${projectId}/chat`);
  return data;
}

const YOU: ThreadParticipant = { kind: "user", name: "You" };

export function toThreadMessages(
  messages: ChatMessage[],
  agent: ThreadParticipant,
): ThreadMessage[] {
  return messages.map((m) => ({
    id: m.id,
    sender: m.role === "user" ? YOU : agent,
    kind: "chat",
    body: m.content,
    createdAt: "",
  }));
}
