import { useDraggable } from "@dnd-kit/core";
import type { SyntheticEvent } from "react";
import { useParams } from "react-router-dom";
import { Badge } from "@/components/ui/Badge";
import type { WorkItem } from "@/lib/api/types";
import { initials, roleVisual } from "@/modules/team/roleVisual";
import { useTeamRoster } from "@/modules/team/useTeamRoster";
import { useAssign } from "./useAssign";

const ATTENTION_STATUSES = new Set(["blocked", "failed"]);

export function TaskCard({ item, onOpen }: { item: WorkItem; onOpen: (id: string) => void }) {
  const { projectId } = useParams();
  const { agents } = useTeamRoster();
  const assign = useAssign(projectId ?? "");
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: item.id });
  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` }
    : undefined;

  const agentList = agents.data ?? [];
  const assignee = agentList.find((a) => a.id === item.assignee_agent_id);
  const stop = (e: SyntheticEvent) => e.stopPropagation();

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`mb-2 cursor-grab rounded-md border border-line bg-surface p-2.5 text-sm shadow-sm transition-shadow hover:shadow-md active:cursor-grabbing ${
        isDragging ? "opacity-50" : ""
      }`}
      {...listeners}
      {...attributes}
    >
      <div className="flex items-start gap-2">
        <button className="flex-1 text-left font-medium text-fg" onClick={() => onOpen(item.id)}>
          {item.title}
        </button>
        {assignee && (
          <span
            title={`${assignee.name} (${roleVisual(assignee.role).label})${
              item.status === "in_progress" ? " — active now" : ""
            }`}
            aria-label={`Assignee ${assignee.name}`}
            className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold text-white${
              item.status === "in_progress" ? " ring-2 ring-accent ring-offset-1 animate-pulse" : ""
            }`}
            style={{ backgroundColor: roleVisual(assignee.role).color }}
          >
            {initials(assignee.name)}
          </span>
        )}
      </div>
      <div className="mt-1.5 flex items-center gap-2">
        {ATTENTION_STATUSES.has(item.status) && <Badge tone="danger">{item.status}</Badge>}
        {agentList.length > 0 && (
          <select
            aria-label="Assignee"
            value={item.assignee_agent_id ?? ""}
            onPointerDown={stop}
            onClick={stop}
            onChange={(e) => assign.mutate({ itemId: item.id, assigneeAgentId: e.target.value || null })}
            className="ml-auto rounded border border-line bg-surface px-1 py-0.5 text-xs text-muted"
          >
            <option value="">Unassigned</option>
            {agentList.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        )}
      </div>
    </div>
  );
}
