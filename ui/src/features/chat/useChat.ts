import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { postChat } from "../../lib/api/chat";
import { workItemKeys } from "../../lib/api/workItems";

export interface Turn {
  role: "user" | "assistant";
  content: string;
}

export function useChat(projectId: string) {
  const qc = useQueryClient();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sessionId, setSessionId] = useState<string | undefined>();

  const send = useMutation({
    mutationFn: (message: string) => postChat(projectId, message, sessionId),
    onMutate: (message) =>
      setTurns((t) => [...t, { role: "user", content: message }]),
    onSuccess: (res) => {
      setSessionId(res.session_id);
      setTurns((t) => [...t, { role: "assistant", content: res.reply }]);
      // Invalidate board work-items so Draft cards appear live
      qc.invalidateQueries({ queryKey: workItemKeys.list(projectId) });
    },
  });

  return { turns, send };
}
