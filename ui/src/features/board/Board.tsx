import { DndContext, type DragEndEvent, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { BOARD_COLUMNS, columnForStatus, groupByColumn } from "./columns";
import { useBoardItems } from "./useBoardItems";
import { useSetStatus } from "./useSetStatus";
import { Column } from "./Column";
import type { WorkItemStatus } from "@/lib/api/types";

export function Board({ projectId, parentId, onOpen }: { projectId: string; parentId?: string; onOpen?: (id: string) => void }) {
  const { data, isLoading, isError, error } = useBoardItems(projectId, parentId);
  const setStatus = useSetStatus(projectId);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  function onDragEnd(e: DragEndEvent) {
    const itemId = String(e.active.id);
    const columnId = e.over ? String(e.over.id) : null;
    if (!columnId || !data) return;
    const item = data.find((i) => i.id === itemId);
    if (!item) return;
    const column = BOARD_COLUMNS.find((c) => c.id === columnId);
    if (!column) return;
    const target = column.statuses[0] as WorkItemStatus;
    if (target === item.status || columnForStatus(item.status) === columnId) return;
    setStatus.mutate({ itemId, status: target });
  }

  if (isLoading) return <p className="p-4 text-sm text-subtle">Loading board…</p>;
  if (isError) return <p className="p-4 text-sm text-danger">{(error as Error).message}</p>;

  const grouped = groupByColumn(data ?? []);
  return (
    <DndContext sensors={sensors} onDragEnd={onDragEnd}>
      <div className="flex gap-3 overflow-x-auto p-4">
        {BOARD_COLUMNS.map((column) => (
          <Column key={column.id} column={column} items={grouped[column.id]} onOpen={onOpen ?? (() => {})} />
        ))}
      </div>
      {setStatus.isError && (
        <p className="px-4 text-sm text-danger">Move rejected: {(setStatus.error as Error).message}</p>
      )}
    </DndContext>
  );
}
