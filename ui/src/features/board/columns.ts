import type { WorkItem, WorkItemStatus } from "../../lib/api/types";

export const ATTENTION = "attention" as const;

export interface BoardColumn {
  id: string;
  title: string;
  /** statuses that live in this column; the first is the drop target status */
  statuses: WorkItemStatus[];
}

export const BOARD_COLUMNS: BoardColumn[] = [
  { id: "draft", title: "Draft", statuses: ["draft"] },
  { id: "refining", title: "Refining", statuses: ["refining"] },
  { id: "ready", title: "Ready", statuses: ["ready"] },
  { id: "in_progress", title: "In Progress", statuses: ["in_progress"] },
  { id: "in_review", title: "In Review", statuses: ["in_review"] },
  { id: "approved", title: "Approved", statuses: ["approved"] },
  { id: "done", title: "Done", statuses: ["done"] },
  { id: ATTENTION, title: "Attention", statuses: ["blocked", "failed"] },
];

const STATUS_TO_COLUMN: Record<WorkItemStatus, string> = Object.fromEntries(
  BOARD_COLUMNS.flatMap((c) => c.statuses.map((s) => [s, c.id])),
) as Record<WorkItemStatus, string>;

export function columnForStatus(status: WorkItemStatus): string {
  return STATUS_TO_COLUMN[status];
}

export function groupByColumn(items: WorkItem[]): Record<string, WorkItem[]> {
  const groups: Record<string, WorkItem[]> = {};
  for (const col of BOARD_COLUMNS) groups[col.id] = [];
  for (const item of items) groups[columnForStatus(item.status)].push(item);
  return groups;
}
