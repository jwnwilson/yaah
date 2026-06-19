import { Outlet } from "react-router-dom";
import { IconButton } from "@/components/ui/IconButton";
import { NotificationBell } from "@/modules/notifications/NotificationBell";
import { Sidebar } from "./Sidebar";

export function AppLayout() {
  return (
    <div className="flex h-screen bg-canvas text-fg">
      <Sidebar />
      <main className="min-h-0 min-w-0 flex-1 overflow-hidden">
        <Outlet />
      </main>
      <div className="fixed right-4 top-3 z-30 flex items-center gap-1">
        <IconButton label="Voice input" title="Voice input">
          <span aria-hidden="true">🎤</span>
        </IconButton>
        <NotificationBell />
      </div>
    </div>
  );
}
