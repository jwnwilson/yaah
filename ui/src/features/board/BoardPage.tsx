import { useState } from "react";
import { useParams, useSearchParams, Link } from "react-router-dom";
import { Board } from "./Board";
import { TicketPanel } from "../work-items/TicketPanel";
import { HierarchyTree } from "../work-items/HierarchyTree";
import { ChatRail } from "../chat/ChatRail";
import { NotificationBell } from "../notifications/NotificationBell";

export default function BoardPage() {
  const { projectId } = useParams();
  const [params, setParams] = useSearchParams();
  const [showChat, setShowChat] = useState(false);
  if (!projectId) return null;

  const openItem = (id: string) => {
    params.set("item", id);
    setParams(params);
  };

  const selectedFeature = params.get("feature") ?? undefined;
  const selectFeature = (id: string | undefined) => {
    if (id) params.set("feature", id); else params.delete("feature");
    setParams(params);
  };

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center gap-3 border-b p-3">
        <Link to="/" className="text-sm text-blue-700">← Projects</Link>
        <h1 className="font-semibold">Board</h1>
        <div className="ml-auto flex items-center gap-2">
          <button
            className="rounded border px-2 py-1 text-sm"
            onClick={() => setShowChat((v) => !v)}
          >
            {showChat ? "Hide chat" : "Team lead"}
          </button>
          <NotificationBell />
        </div>
      </header>
      <div className="flex flex-1 overflow-hidden">
        <HierarchyTree projectId={projectId} selectedFeature={selectedFeature} onSelectFeature={selectFeature} />
        <div className="flex-1 overflow-auto">
          <Board projectId={projectId} parentId={selectedFeature} onOpen={openItem} />
        </div>
        {showChat && <ChatRail projectId={projectId} />}
      </div>
      {params.get("item") && (
        <TicketPanel
          projectId={projectId}
          itemId={params.get("item")!}
          onClose={() => { params.delete("item"); setParams(params); }}
        />
      )}
    </div>
  );
}
