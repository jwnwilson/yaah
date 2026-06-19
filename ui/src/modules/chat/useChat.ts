import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type { ThreadMessage, ThreadParticipant } from "@/components/ui/chat/types";
import { backlogKeys } from "@/lib/api/backlog";
import {
  listMessages,
  listSessions,
  postChat,
  toThreadMessages,
  type EpicSpecEdit,
  type ProposedUpdate,
} from "@/lib/api/chat";
import { epicKeys } from "@/lib/api/epics";
import { workItemDetailKey } from "@/lib/api/workItemDetail";
import { updateWorkItem, workItemKeys } from "@/lib/api/workItems";

const LEAD: ThreadParticipant = { kind: "agent", id: "lead", name: "Team Lead", role: "lead" };
const YOU: ThreadParticipant = { kind: "user", name: "You" };

export function useChat(projectId: string, epicId?: string) {
  const qc = useQueryClient();
  const [messages, setMessages] = useState<ThreadMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [proposedEpicUpdate, setProposedEpicUpdate] = useState<EpicSpecEdit | null>(null);
  const [proposedUpdates, setProposedUpdates] = useState<ProposedUpdate[]>([]);

  const sessions = useQuery({
    queryKey: ["chat-sessions", projectId, epicId ?? null],
    queryFn: () => listSessions(projectId),
  });

  useEffect(() => {
    if (!sessions.data || sessionId) return;
    const match = sessions.data.find((s) => (epicId ? s.epic_id === epicId : !s.epic_id));
    if (!match) return;
    setSessionId(match.id);
    listMessages(match.id).then((msgs) => setMessages(toThreadMessages(msgs, LEAD)));
  }, [sessions.data, sessionId, epicId]);

  const refreshBoard = () => {
    qc.invalidateQueries({ queryKey: workItemKeys.list(projectId) });
    qc.invalidateQueries({ queryKey: backlogKeys.view(projectId) });
    if (epicId) qc.invalidateQueries({ queryKey: epicKeys.board(epicId) });
  };

  const send = useMutation({
    mutationFn: (message: string) => postChat(projectId, message, sessionId, epicId),
    onMutate: (message) =>
      setMessages((m) => [
        ...m,
        { id: `local-${m.length}`, sender: YOU, kind: "chat", body: message, createdAt: "" },
      ]),
    onSuccess: (res) => {
      setSessionId(res.session_id);
      setMessages((m) => [
        ...m,
        { id: res.session_id + "-r" + m.length, sender: LEAD, kind: "chat", body: res.reply, createdAt: "" },
      ]);
      setProposedEpicUpdate(res.proposed_epic_update ?? null);
      setProposedUpdates(res.proposed_updates ?? []);
      refreshBoard();
    },
  });

  const acceptEpicUpdate = useMutation({
    mutationFn: () =>
      updateWorkItem(epicId as string, {
        body: proposedEpicUpdate?.body ?? undefined,
        acceptance_criteria: proposedEpicUpdate?.acceptance_criteria ?? undefined,
      }),
    onSuccess: () => {
      setProposedEpicUpdate(null);
      if (epicId) qc.invalidateQueries({ queryKey: epicKeys.board(epicId) });
    },
  });

  const dismissEpicUpdate = () => setProposedEpicUpdate(null);

  const applyUpdate = useMutation({
    mutationFn: (u: ProposedUpdate) =>
      updateWorkItem(u.id, {
        title: u.title ?? undefined,
        body: u.body ?? undefined,
        acceptance_criteria: u.acceptance_criteria ?? undefined,
      }),
    onSuccess: (_data, u) => {
      setProposedUpdates((list) => list.filter((x) => x.id !== u.id));
      qc.invalidateQueries({ queryKey: workItemDetailKey(u.id) });
      refreshBoard();
    },
  });

  const dismissUpdate = (id: string) =>
    setProposedUpdates((list) => list.filter((x) => x.id !== id));

  return {
    messages,
    send,
    processing: send.isPending ? { name: LEAD.name } : null,
    proposedEpicUpdate,
    acceptEpicUpdate,
    dismissEpicUpdate,
    proposedUpdates,
    applyUpdate,
    dismissUpdate,
  };
}
