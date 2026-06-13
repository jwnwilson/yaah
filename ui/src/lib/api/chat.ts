import { apiGetPage, apiPost } from "./client";

export interface ChatTurn {
  session_id: string;
  reply: string;
  created_items: unknown[];
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
): Promise<ChatTurn> {
  return apiPost<ChatTurn>(`/projects/${projectId}/chat`, {
    message,
    session_id: sessionId,
  });
}

export async function listMessages(sessionId: string): Promise<ChatMessage[]> {
  const { data } = await apiGetPage<ChatMessage[]>(
    `/chat/${sessionId}/messages?page_size=200`,
  );
  return data;
}
