import { useQuery } from "@tanstack/react-query";
import { agentKeys, getAgent } from "@/lib/api/agents";
import { messageKeys, listSentMessages } from "@/lib/api/messages";

export function useAgent(id: string) {
  return useQuery({ queryKey: agentKeys.detail(id), queryFn: () => getAgent(id), enabled: Boolean(id) });
}

export function useSentMessages(id: string) {
  return useQuery({
    queryKey: messageKeys.sent(id),
    queryFn: () => listSentMessages(id),
    enabled: Boolean(id),
  });
}
