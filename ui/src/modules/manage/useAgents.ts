import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { agentKeys, listAgents, updateAgent, type UpdateAgentInput } from "@/lib/api/agents";
import { teamKeys, listTeams } from "@/lib/api/teams";

export function useTeams() {
  return useQuery({ queryKey: teamKeys.all, queryFn: listTeams });
}

export function useAgents(teamId: string | undefined) {
  return useQuery({
    queryKey: agentKeys.forTeam(teamId ?? ""),
    queryFn: () => listAgents(teamId as string),
    enabled: Boolean(teamId),
  });
}

export function useUpdateAgent(teamId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (a: { id: string; input: UpdateAgentInput }) => updateAgent(a.id, a.input),
    onSuccess: () => qc.invalidateQueries({ queryKey: agentKeys.forTeam(teamId) }),
  });
}
