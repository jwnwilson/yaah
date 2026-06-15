import { useState } from "react";
import { useParams, useSearchParams, Link } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { ChatRail } from "@/modules/chat/ChatRail";
import { HierarchyTree } from "@/modules/work-items/HierarchyTree";
import { TicketPanel } from "@/modules/work-items/TicketPanel";
import { Board } from "./Board";
import { EpicContextBand } from "./EpicContextBand";
import { useEpicBoard } from "./useEpicBoard";

export default function BoardPage() {
  const { projectId } = useParams();
  const [params, setParams] = useSearchParams();
  const [showChat, setShowChat] = useState(false);
  const selectedEpic = params.get("epic") ?? undefined;
  const selectedFeature = params.get("feature") ?? undefined;
  const epicBoard = useEpicBoard(projectId ?? "", selectedEpic);
  if (!projectId) return null;

  const openItem = (id: string) => {
    params.set("item", id);
    setParams(params);
  };
  const selectEpic = (id: string | undefined) => {
    if (id) params.set("epic", id);
    else params.delete("epic");
    params.delete("feature");
    setParams(params);
  };
  const selectFeature = (id: string | undefined) => {
    if (id) params.set("feature", id);
    else params.delete("feature");
    setParams(params);
  };

  const epicTasks = selectedEpic
    ? selectedFeature
      ? (epicBoard.data?.tasks ?? []).filter((t) => t.parent_id === selectedFeature)
      : epicBoard.data?.tasks ?? []
    : undefined;

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
        <HierarchyTree
          projectId={projectId}
          selectedEpic={selectedEpic}
          onSelectEpic={selectEpic}
          selectedFeature={selectedFeature}
          onSelectFeature={selectFeature}
        />
        <div className="flex flex-1 flex-col overflow-hidden">
          {selectedEpic && (
            <EpicContextBand
              projectId={projectId}
              epicId={selectedEpic}
              selectedFeature={selectedFeature}
              onSelectFeature={selectFeature}
              onEditEpic={openItem}
            />
          )}
          <div className="flex-1 overflow-auto">
            <Board projectId={projectId} parentId={selectedFeature} items={epicTasks} onOpen={openItem} />
          </div>
        </div>
        {showChat && <ChatRail projectId={projectId} epicId={selectedEpic} />}
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
