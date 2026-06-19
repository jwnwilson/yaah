import { useState } from "react";
import { Link } from "react-router-dom";
import { IconButton } from "@/components/ui/IconButton";
import type { Message } from "@/lib/api/messages";
import { relativeTime } from "@/modules/runs/RunEventRow";
import { useUserNotices, useUserUnreadCount } from "./useNotifications";

function SeverityChip({ severity }: { severity: Message["severity"] }) {
  if (severity === "info") return null;
  const className =
    severity === "critical"
      ? "text-danger"
      : "text-warning";
  const label = severity === "critical" ? "Critical" : "Attention";
  return (
    <span className={`text-[10px] font-semibold uppercase tracking-wide ${className}`}>{label}</span>
  );
}

function NoticeBody({ notice }: { notice: Message }) {
  const isGate = notice.kind === "gate";
  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center gap-2">
        <span className="text-sm text-fg">{notice.subject}</span>
        <SeverityChip severity={notice.severity} />
      </div>
      {isGate && (
        <span className="text-[10px] font-semibold uppercase tracking-wide text-warning">
          Approval needed
        </span>
      )}
      <span className="text-[10px] text-subtle">{relativeTime(notice.created_at)}</span>
    </div>
  );
}

function NoticeItem({ notice }: { notice: Message }) {
  if (notice.run_id) {
    return (
      <li>
        <Link to={`/runs/${notice.run_id}`} className="block px-3 py-2 hover:bg-surface-hover">
          <NoticeBody notice={notice} />
        </Link>
      </li>
    );
  }
  return (
    <li className="px-3 py-2">
      <NoticeBody notice={notice} />
    </li>
  );
}

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const { data: count = 0 } = useUserUnreadCount();
  const { data: notices = [], isLoading } = useUserNotices(open);

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
        <div className="absolute right-0 z-20 mt-2 w-72 overflow-hidden rounded-lg border border-line bg-surface shadow-lg">
          <div className="border-b border-line px-3 py-2 text-xs font-semibold uppercase tracking-wide text-subtle">
            Notifications
          </div>
          {isLoading && <p className="px-3 py-2 text-sm text-subtle">Loading…</p>}
          {!isLoading && notices.length === 0 && (
            <p className="px-3 py-2 text-sm text-subtle">No notifications.</p>
          )}
          <ul className="max-h-80 divide-y divide-line overflow-auto">
            {notices.map((n) => (
              <NoticeItem key={n.id} notice={n} />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
