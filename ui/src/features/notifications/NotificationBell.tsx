import { useState } from "react";
import { Link } from "react-router-dom";
import type { Notification } from "../../lib/api/notifications";
import { useNotifications, useUnreadCount } from "./useNotifications";

function NotificationItem({ notification }: { notification: Notification }) {
  const { category, title, action } = notification;
  const label = (
    <div className="flex flex-col">
      <span className="text-[10px] font-semibold uppercase text-gray-400">{category}</span>
      <span className="text-sm">{title}</span>
    </div>
  );

  if (action?.kind === "gate_approval") {
    return (
      <li>
        <Link
          to={`/runs/${action.run_id}`}
          className="block rounded px-3 py-2 hover:bg-gray-50"
        >
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
      <button
        type="button"
        aria-label={`${count} unread notifications`}
        aria-expanded={open}
        className="relative rounded p-1 text-gray-600 hover:bg-gray-100"
        onClick={() => setOpen((v) => !v)}
      >
        <span aria-hidden="true">🔔</span>
        {count > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-semibold text-white">
            {count}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-10 mt-2 w-72 rounded border bg-white shadow-lg">
          <div className="border-b px-3 py-2 text-xs font-semibold uppercase text-gray-500">
            Notifications
          </div>
          {isLoading && <p className="px-3 py-2 text-sm text-gray-500">Loading…</p>}
          {!isLoading && notifications.length === 0 && (
            <p className="px-3 py-2 text-sm text-gray-500">No notifications.</p>
          )}
          <ul className="max-h-80 divide-y overflow-auto">
            {notifications.map((n) => (
              <NotificationItem key={n.id} notification={n} />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
