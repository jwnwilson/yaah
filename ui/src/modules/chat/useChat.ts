import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { postChat, type EpicSpecEdit } from "@/lib/api/chat";
import { epicKeys } from "@/lib/api/epics";
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

  const send = useMutation({
    mutationFn: (message: string) => postChat(projectId, message, sessionId, epicId),
    onMutate: (message) =>
      setTurns((t) => [...t, { role: "user", content: message }]),
    onSuccess: (res) => {
      setSessionId(res.session_id);
      setTurns((t) => [...t, { role: "assistant", content: res.reply }]);
      setProposedEpicUpdate(res.proposed_epic_update ?? null);
      qc.invalidateQueries({ queryKey: workItemKeys.list(projectId) });
      if (epicId) qc.invalidateQueries({ queryKey: epicKeys.board(epicId) });
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

  return { turns, send, proposedEpicUpdate, acceptEpicUpdate, dismissEpicUpdate };
}
