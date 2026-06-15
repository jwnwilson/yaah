import { useQuery } from "@tanstack/react-query";
import { epicKeys, getEpicBoard } from "@/lib/api/epics";

export function useEpicBoard(projectId: string, epicId: string | undefined) {
  return useQuery({
    queryKey: epicId ? epicKeys.board(epicId) : (["epic-board", "none"] as const),
    queryFn: () => getEpicBoard(projectId, epicId as string),
    enabled: Boolean(epicId),
  });
}
