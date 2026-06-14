import { useDraggable } from "@dnd-kit/core";
import type { WorkItem } from "../../lib/api/types";
import { Badge } from "../../ui/Badge";

const ATTENTION_STATUSES = new Set(["blocked", "failed"]);

export function TaskCard({ item, onOpen }: { item: WorkItem; onOpen: (id: string) => void }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: item.id });
  const style = transform ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` } : undefined;
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
      <button className="text-left font-medium text-fg" onClick={() => onOpen(item.id)}>
        {item.title}
      </button>
      {ATTENTION_STATUSES.has(item.status) && (
        <Badge tone="danger" className="ml-2">
          {item.status}
        </Badge>
      )}
    </div>
  );
}
