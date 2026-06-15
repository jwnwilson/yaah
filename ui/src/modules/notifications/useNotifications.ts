import { useQuery } from "@tanstack/react-query";
import {
  getUnreadCount,
  listNotifications,
  notificationKeys,
} from "@/lib/api/notifications";

// Poll the unread count on the same cadence the board uses to stay fresh
// without SSE (deferred for A5e).
const UNREAD_COUNT_POLL_MS = 15_000;

export function useUnreadCount() {
  return useQuery({
    queryKey: notificationKeys.unreadCount,
    queryFn: getUnreadCount,
    refetchInterval: UNREAD_COUNT_POLL_MS,
  });
}

export function useNotifications(enabled = true) {
  return useQuery({
    queryKey: notificationKeys.list,
    queryFn: listNotifications,
    enabled,
  });
}
