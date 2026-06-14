import { useState } from "react";
import { Link } from "react-router-dom";
import type { Notification } from "../../lib/api/notifications";
import { IconButton } from "../../ui/IconButton";
import { useNotifications, useUnreadCount } from "./useNotifications";

function NotificationItem({ notification }: { notification: Notification }) {
  const { category, title, action } = notification;
  const label = (
    <div className="flex flex-col">
      <span className="text-[10px] font-semibold uppercase tracking-wide text-subtle">{category}</span>
      <span className="text-sm text-fg">{title}</span>
    </div>
  );

  if (action?.kind === "gate_approval") {
    return (
      <li>
        <Link to={`/runs/${action.run_id}`} className="block px-3 py-2 hover:bg-surface-hover">
          {label}
        </Link>
      </li>
    );
  }

  return <li className="px-3 py-2">{label}</li>;
}

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const { data: count = 0 } = useUnreadCount();
  const { data: notifications = [], isLoading } = useNotifications(open);

  return (
    <div className="relative">
      <IconButton
        label={`${count} unread notifications`}
        aria-expanded={open}
        className="relative"
        onClick={() => setOpen((v) => !v)}
      >
        <span aria-hidden="true">🔔</span>
        {count > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-semibold text-danger-fg">
            {count}
          </span>
        )}
      </IconButton>
      {open && (
        <div className="absolute right-0 z-10 mt-2 w-72 overflow-hidden rounded-lg border border-line bg-surface shadow-lg">
          <div className="border-b border-line px-3 py-2 text-xs font-semibold uppercase tracking-wide text-subtle">
            Notifications
          </div>
          {isLoading && <p className="px-3 py-2 text-sm text-subtle">Loading…</p>}
          {!isLoading && notifications.length === 0 && (
            <p className="px-3 py-2 text-sm text-subtle">No notifications.</p>
          )}
          <ul className="max-h-80 divide-y divide-line overflow-auto">
            {notifications.map((n) => (
              <NotificationItem key={n.id} notification={n} />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
