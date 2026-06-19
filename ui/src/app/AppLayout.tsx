import { Outlet, useNavigate } from "react-router-dom";
import { IconButton } from "@/components/ui/IconButton";
import { ChatLauncherProvider, useChatLauncher } from "@/modules/chat/ChatLauncherContext";
import { NotificationBell } from "@/modules/notifications/NotificationBell";
import { useCurrentProjectId } from "@/modules/projects/useCurrentProject";
import { Sidebar } from "./Sidebar";

function VoiceShortcut() {
  const { openChat } = useChatLauncher();
  const navigate = useNavigate();
  const projectId = useCurrentProjectId();
  return (
    <IconButton
      label="Talk to the team lead"
      title="Talk to the team lead"
      onClick={() => {
        openChat(true);
        if (projectId) navigate(`/projects/${projectId}`);
      }}
    >
      <span aria-hidden="true">🎤</span>
    </IconButton>
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
