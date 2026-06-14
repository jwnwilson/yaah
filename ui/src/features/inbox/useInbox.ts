import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  messageKeys,
  listMessages,
  markMessageRead,
  sendMessage,
  type SendMessageInput,
} from "../../lib/api/messages";

export function useMessages(box: string) {
  return useQuery({
    queryKey: messageKeys.list(box),
    queryFn: () => listMessages(box),
    enabled: Boolean(box),
  });
}

export function useMarkRead(box: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => markMessageRead(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: messageKeys.list(box) });
      qc.invalidateQueries({ queryKey: messageKeys.unread(box) });
    },
  });
}

export function useSendMessage(box: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: SendMessageInput) => sendMessage(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: messageKeys.list(box) }),
  });
}
