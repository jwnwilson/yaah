import { apiGetPage, apiPost } from "./client";

export interface EpicSpecEdit {
  body?: string | null;
  acceptance_criteria?: string[] | null;
}

export interface ChatTurn {
  session_id: string;
  reply: string;
  created_items: unknown[];
  proposed_epic_update?: EpicSpecEdit | null;
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
