export type ThreadParticipantKind = "user" | "agent" | "system";

export interface ThreadParticipant {
  kind: ThreadParticipantKind;
  id?: string; // agent id when kind === "agent"
  name: string;
  role?: string;
}

export type ThreadMessageKind =
  | "chat"
  | "dispatch"
  | "report"
  | "status"
  | "notice"
  | "gate";

export interface ThreadMessage {
  id: string;
  sender: ThreadParticipant;
  recipient?: ThreadParticipant; // set for multi-party mailbox traffic
  kind: ThreadMessageKind;
  body: string;
  severity?: "info" | "attention" | "critical";
  createdAt: string; // ISO timestamp
}
