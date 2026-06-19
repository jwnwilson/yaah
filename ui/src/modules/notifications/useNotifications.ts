import { useQuery } from "@tanstack/react-query";
import { getMessageUnreadCount, listMessages, messageKeys } from "@/lib/api/messages";

// The notification bell reads the user's mailbox (box="me"): notices and gate
// approvals land there as user-recipient messages.
const USER_BOX = "me";

// Poll the unread count on the same cadence the board uses to stay fresh
// without SSE (deferred for A5e).
const UNREAD_COUNT_POLL_MS = 15_000;

export function useUserUnreadCount() {
  return useQuery({
    queryKey: messageKeys.unread(USER_BOX),
    queryFn: () => getMessageUnreadCount(USER_BOX),
    refetchInterval: UNREAD_COUNT_POLL_MS,
  });
}

export function useUserNotices(enabled = true) {
  return useQuery({
    queryKey: messageKeys.list(USER_BOX),
    queryFn: () => listMessages(USER_BOX),
    enabled,
  });
}
