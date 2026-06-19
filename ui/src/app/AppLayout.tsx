import { Outlet, useNavigate } from "react-router-dom";
import { IconButton } from "@/components/ui/IconButton";
import { ChatLauncherProvider, useChatLauncher } from "@/modules/chat/ChatLauncherContext";
import { NotificationBell } from "@/modules/notifications/NotificationBell";
import { useCurrentProjectId } from "@/modules/projects/useCurrentProject";
import { Sidebar } from "./Sidebar";

function VoiceShortcut() {
  const { openChat, listening } = useChatLauncher();
  const navigate = useNavigate();
  const projectId = useCurrentProjectId();
  return (
    <div className="flex items-center gap-1">
      {listening && (
        <span
          role="status"
          aria-live="polite"
          className="flex items-center gap-1 rounded-full bg-danger/10 px-2 py-0.5 text-xs font-medium text-danger"
        >
          <span aria-hidden="true" className="h-1.5 w-1.5 animate-pulse rounded-full bg-danger" />
          Listening…
        </span>
      )}
      <IconButton
        label="Talk to the team lead"
        title="Talk to the team lead"
        className={listening ? "text-danger" : undefined}
        onClick={() => {
          openChat(true);
          if (projectId) navigate(`/projects/${projectId}`);
        }}
      >
        <span aria-hidden="true">🎤</span>
      </IconButton>
    </div>
  );
}

export function AppLayout() {
  return (
    <ChatLauncherProvider>
      <div className="flex h-screen bg-canvas text-fg">
        <Sidebar />
        <main className="min-h-0 min-w-0 flex-1 overflow-hidden">
          <Outlet />
        </main>
        <div className="fixed right-4 top-3 z-30 flex items-center gap-1">
          <VoiceShortcut />
          <NotificationBell />
        </div>
      </div>
    </ChatLauncherProvider>
  );
}
