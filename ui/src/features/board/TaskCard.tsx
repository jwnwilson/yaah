import { useDraggable } from "@dnd-kit/core";
import type { WorkItem } from "../../lib/api/types";

const ATTENTION_STATUSES = new Set(["blocked", "failed"]);

export function TaskCard({ item, onOpen }: { item: WorkItem; onOpen: (id: string) => void }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: item.id });
  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` }
    : undefined;
  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`mb-2 rounded border bg-white p-2 text-sm shadow-sm ${isDragging ? "opacity-50" : ""}`}
      {...listeners}
      {...attributes}
    >
      <button className="text-left font-medium" onClick={() => onOpen(item.id)}>
        {item.title}
      </button>
      {ATTENTION_STATUSES.has(item.status) && (
        <span className="ml-2 rounded bg-red-100 px-1.5 py-0.5 text-xs text-red-700">
          {item.status}
        </span>
      )}
    </div>
  );
}
