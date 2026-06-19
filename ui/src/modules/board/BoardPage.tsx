import { useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";
import { DetailPeek } from "@/modules/backlog/DetailPeek";
import { ChatRail } from "@/modules/chat/ChatRail";
import { HierarchyTree } from "@/modules/work-items/HierarchyTree";
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
      <PageHeader
        title="Board"
        actions={
          <Button size="sm" variant="secondary" onClick={() => setShowChat((v) => !v)}>
            {showChat ? "Hide chat" : "Team lead"}
          </Button>
        }
      />
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
              onEditItem={openItem}
            />
          )}
          <div className="flex-1 overflow-auto">
            <Board projectId={projectId} parentId={selectedFeature} items={epicTasks} onOpen={openItem} />
          </div>
        </div>
        {showChat && <ChatRail projectId={projectId} epicId={selectedEpic} />}
      </div>
      {params.get("item") && (
        <DetailPeek
          projectId={projectId}
          itemId={params.get("item")!}
          onClose={() => { params.delete("item"); setParams(params); }}
        />
      )}
    </div>
  );
}
