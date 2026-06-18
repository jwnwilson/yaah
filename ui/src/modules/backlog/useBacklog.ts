import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  activateEpic,
  backlogKeys,
  deactivateEpic,
  getBacklog,
} from "@/lib/api/backlog";
import { updateProject } from "@/lib/api/projects";

export function useBacklog(projectId: string) {
  const qc = useQueryClient();
  const invalidate = () =>
    qc.invalidateQueries({ queryKey: backlogKeys.view(projectId) });

  const query = useQuery({
    queryKey: backlogKeys.view(projectId),
    queryFn: () => getBacklog(projectId),
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

  return { query, activate, deactivate, setCap };
}
