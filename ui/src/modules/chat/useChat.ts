import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { backlogKeys } from "@/lib/api/backlog";
import { postChat, type EpicSpecEdit, type ProposedUpdate } from "@/lib/api/chat";
import { epicKeys } from "@/lib/api/epics";
import { workItemDetailKey } from "@/lib/api/workItemDetail";
import { updateWorkItem, workItemKeys } from "@/lib/api/workItems";

export interface Turn {
  role: "user" | "assistant";
  content: string;
}

export function useChat(projectId: string, epicId?: string) {
  const qc = useQueryClient();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [proposedEpicUpdate, setProposedEpicUpdate] = useState<EpicSpecEdit | null>(null);
  const [proposedUpdates, setProposedUpdates] = useState<ProposedUpdate[]>([]);

  const refreshBoard = () => {
    qc.invalidateQueries({ queryKey: workItemKeys.list(projectId) });
    qc.invalidateQueries({ queryKey: backlogKeys.view(projectId) });
    if (epicId) qc.invalidateQueries({ queryKey: epicKeys.board(epicId) });
  };

  const send = useMutation({
    mutationFn: (message: string) => postChat(projectId, message, sessionId, epicId),
    onMutate: (message) => setTurns((t) => [...t, { role: "user", content: message }]),
    onSuccess: (res) => {
      setSessionId(res.session_id);
      setTurns((t) => [...t, { role: "assistant", content: res.reply }]);
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
    turns,
    send,
    proposedEpicUpdate,
    acceptEpicUpdate,
    dismissEpicUpdate,
    proposedUpdates,
    applyUpdate,
    dismissUpdate,
  };
}
