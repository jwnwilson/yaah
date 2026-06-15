import { useQuery } from "@tanstack/react-query";
import { teamKeys, listTeams } from "@/lib/api/teams";
import { agentKeys, listAgents } from "@/lib/api/agents";

/** First team's roster (single-team for now; multi-team selection is future work). */
export function useTeamRoster() {
  const teams = useQuery({ queryKey: teamKeys.all, queryFn: listTeams });
  const teamId = teams.data?.[0]?.id;
  const agents = useQuery({
    queryKey: agentKeys.forTeam(teamId ?? ""),
    queryFn: () => listAgents(teamId as string),
    enabled: Boolean(teamId),
  });
  return { teams, teamId, agents };
}
