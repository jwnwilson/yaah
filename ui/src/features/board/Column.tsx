import { useDroppable } from "@dnd-kit/core";
import type { BoardColumn } from "./columns";
import type { WorkItem } from "../../lib/api/types";
import { TaskCard } from "./TaskCard";

export function Column({
  column,
  items,
  onOpen,
}: {
  column: BoardColumn;
  items: WorkItem[];
  onOpen: (id: string) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: column.id });
  return (
    <div
      ref={setNodeRef}
      className={`flex w-60 shrink-0 flex-col rounded-lg border border-line bg-panel p-2 transition-shadow ${
        isOver ? "ring-2 ring-accent" : ""
      }`}
    >
      <div className="mb-2 flex items-center justify-between px-1">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-subtle">{column.title}</h2>
        <span className="rounded-full bg-surface-hover px-1.5 text-xs text-fg">{items.length}</span>
      </div>
      {items.map((item) => (
        <TaskCard key={item.id} item={item} onOpen={onOpen} />
      ))}
    </div>
  );
}
