import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { agentKeys, listAgents } from "@/lib/api/agents";
import { DetailPeek } from "@/modules/backlog/DetailPeek";
import { useBacklog } from "@/modules/backlog/useBacklog";
import { useChatLauncher } from "@/modules/chat/ChatLauncherContext";
import { ChatRail } from "@/modules/chat/ChatRail";
import { useProjects } from "@/modules/projects/useProjects";
import { ActivePopover } from "./ActivePopover";
import { Board } from "./Board";
import { deriveBoard } from "./boardData";

export default function BoardPage() {
  const { projectId } = useParams();
  const [params, setParams] = useSearchParams();
  const { open, toggle, dictate, consumeDictate, setListening } = useChatLauncher();
  const [epicFilter, setEpicFilter] = useState("");
  const [featureFilter, setFeatureFilter] = useState("");
  const [agentFilter, setAgentFilter] = useState("");

  const { query, activate, deactivate } = useBacklog(projectId ?? "");
  const { data: projects } = useProjects();
  const teamId = projects?.find((p) => p.id === projectId)?.team_id ?? undefined;
  const agents = useQuery({
    queryKey: agentKeys.forTeam(teamId ?? ""),
    queryFn: () => listAgents(teamId!),
    enabled: !!teamId,
  });

  const board = useMemo(() => deriveBoard(query.data), [query.data]);

  if (!projectId) return null;

  const openItem = (id: string) => {
    params.set("item", id);
    setParams(params);
  };

  const visibleFeatures = epicFilter
    ? board.featureOptions.filter((f) => f.epicId === epicFilter)
    : board.featureOptions;

  const tasks = board.tasks.filter((t) => {
    if (epicFilter && board.taskEpicId[t.id] !== epicFilter) return false;
    if (featureFilter && t.parent_id !== featureFilter) return false;
    if (agentFilter && t.assignee_agent_id !== agentFilter) return false;
    return true;
  });

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Board"
        actions={
          <Button size="sm" variant="secondary" onClick={toggle}>
            {open ? "Hide chat" : "Team lead"}
          </Button>
        }
      />
      <div className="flex items-center gap-2 border-b border-line bg-surface px-4 py-2">
        <Select
          aria-label="filter by epic"
          value={epicFilter}
          onChange={(e) => {
            setEpicFilter(e.target.value);
            setFeatureFilter("");
          }}
          className="w-44"
        >
          <option value="">All epics</option>
          {board.epicOptions.map((o) => (
            <option key={o.id} value={o.id}>
              {o.title}
            </option>
          ))}
        </Select>
        <Select
          aria-label="filter by feature"
          value={featureFilter}
          onChange={(e) => setFeatureFilter(e.target.value)}
          className="w-44"
        >
          <option value="">All features</option>
          {visibleFeatures.map((o) => (
            <option key={o.id} value={o.id}>
              {o.title}
            </option>
          ))}
        </Select>
        <Select
          aria-label="filter by agent"
          value={agentFilter}
          onChange={(e) => setAgentFilter(e.target.value)}
          className="w-40"
        >
          <option value="">All agents</option>
          {agents.data?.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </Select>
        <div className="ml-auto">
          <ActivePopover
            data={query.data}
            onActivate={(id) => activate.mutate(id)}
            onDeactivate={(id) => deactivate.mutate(id)}
          />
        </div>
      </div>
      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 overflow-auto">
          {query.isError ? (
            <p className="p-4 text-sm text-danger">{(query.error as Error).message}</p>
          ) : (
            <Board projectId={projectId} items={tasks} onOpen={openItem} />
          )}
        </div>
        {open && (
          <ChatRail
            projectId={projectId}
            autoDictate={dictate}
            onDictateConsumed={consumeDictate}
            onListeningChange={setListening}
          />
        )}
      </div>
      {params.get("item") && (
        <DetailPeek
          projectId={projectId}
          itemId={params.get("item")!}
          onClose={() => {
            params.delete("item");
            setParams(params);
          }}
        />
      )}
    </div>
  );
}
