import { useState } from "react";
import { useParams, useSearchParams, Link } from "react-router-dom";
import { ChatRail } from "@/features/chat/ChatRail";
import { HierarchyTree } from "@/features/work-items/HierarchyTree";
import { TicketPanel } from "@/features/work-items/TicketPanel";
import { Button } from "@/ui/Button";
import { Board } from "./Board";

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
    <div className="flex h-full flex-col">
      <header className="flex items-center gap-3 border-b border-line bg-surface px-4 py-3">
        <Link to="/" className="text-sm text-accent hover:underline">← Projects</Link>
        <h1 className="font-semibold text-fg">Board</h1>
        <div className="ml-auto flex items-center gap-2">
          <Button size="sm" variant="secondary" onClick={() => setShowChat((v) => !v)}>
            {showChat ? "Hide chat" : "Team lead"}
          </Button>
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
