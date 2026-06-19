import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  activateEpic,
  backlogKeys,
  deactivateEpic,
  getBacklog,
  reorderWorkItems,
} from "@/lib/api/backlog";
import { updateProject } from "@/lib/api/projects";
import type { WorkItemKind, WorkItemStatus } from "@/lib/api/types";
import {
  createWorkItem,
  deleteWorkItem,
  setWorkItemStatus,
  updateWorkItem,
} from "@/lib/api/workItems";

export function useBacklog(projectId: string) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: backlogKeys.view(projectId) });

  const query = useQuery({
    queryKey: backlogKeys.view(projectId),
    queryFn: () => getBacklog(projectId),
  });

  const create = useMutation({
    mutationFn: (v: { kind: WorkItemKind; title: string; parent_id?: string }) =>
      createWorkItem(projectId, v),
    onSuccess: invalidate,
  });

  const rename = useMutation({
    mutationFn: (v: { id: string; title: string }) => updateWorkItem(v.id, { title: v.title }),
    onSuccess: invalidate,
  });

  const setStatus = useMutation({
    mutationFn: (v: { id: string; status: WorkItemStatus }) => setWorkItemStatus(v.id, v.status),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteWorkItem(id),
    onSuccess: invalidate,
  });

  const reorder = useMutation({
    mutationFn: (v: { parentId: string | null; orderedIds: string[] }) =>
      reorderWorkItems(projectId, v.parentId, v.orderedIds),
    onSuccess: invalidate,
  });

  const activate = useMutation({
    mutationFn: (epicId: string) => activateEpic(projectId, epicId),
    onSuccess: invalidate,
  });

  const deactivate = useMutation({
    mutationFn: (epicId: string) => deactivateEpic(projectId, epicId),
    onSuccess: invalidate,
  });

  const setCap = useMutation({
    mutationFn: (max: number) => updateProject(projectId, { max_concurrent_runs: max }),
    onSuccess: invalidate,
  });

  return { query, create, rename, setStatus, remove, reorder, activate, deactivate, setCap };
}

export type BacklogActions = ReturnType<typeof useBacklog>;
