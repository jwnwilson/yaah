import { useQuery } from "@tanstack/react-query";
import { listProjects, projectKeys } from "../../lib/api/projects";

export function useProjects() {
  return useQuery({ queryKey: projectKeys.all, queryFn: listProjects });
}
