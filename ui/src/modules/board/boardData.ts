import type { BacklogView } from "@/lib/api/backlog";
import type { WorkItem } from "@/lib/api/types";

export interface EpicOption {
  id: string;
  title: string;
}
export interface FeatureOption {
  id: string;
  title: string;
  epicId: string;
}

export interface BoardData {
  /** Tasks shown on the board: those under an active epic or an active feature. */
  tasks: WorkItem[];
  /** Active epics, for the epic filter. */
  epicOptions: EpicOption[];
  /** Features on the board (under an active epic, or themselves active), for the feature filter. */
  featureOptions: FeatureOption[];
  /** task id -> owning epic id, for filtering by epic. */
  taskEpicId: Record<string, string>;
}

/** Derive the board (active work) from the backlog tree. A task is on the board when its
 * epic OR its feature is active. */
export function deriveBoard(view?: BacklogView): BoardData {
  const tasks: WorkItem[] = [];
  const epicOptions: EpicOption[] = [];
  const featureOptions: FeatureOption[] = [];
  const taskEpicId: Record<string, string> = {};
  if (!view) return { tasks, epicOptions, featureOptions, taskEpicId };

  for (const be of view.epics) {
    if (be.active) epicOptions.push({ id: be.epic.id, title: be.epic.title });
    if (be.active) {
      for (const t of be.tasks) {
        tasks.push(t);
        taskEpicId[t.id] = be.epic.id;
      }
    }
    for (const bf of be.features) {
      if (be.active || bf.feature.active) {
        featureOptions.push({ id: bf.feature.id, title: bf.feature.title, epicId: be.epic.id });
        for (const t of bf.tasks) {
          tasks.push(t);
          taskEpicId[t.id] = be.epic.id;
        }
      }
    }
  }
  return { tasks, epicOptions, featureOptions, taskEpicId };
}
