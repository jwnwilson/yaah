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
      className={`flex w-56 shrink-0 flex-col rounded bg-gray-50 p-2 ${isOver ? "ring-2 ring-blue-400" : ""}`}
    >
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
        {column.title}
      </h2>
      {items.map((item) => (
        <TaskCard key={item.id} item={item} onOpen={onOpen} />
      ))}
    </div>
  );
}
