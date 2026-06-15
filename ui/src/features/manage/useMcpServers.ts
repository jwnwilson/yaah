import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createMcpServer, deleteMcpServer, listMcpServers, mcpServerKeys, updateMcpServer,
  type CreateMcpServerInput, type UpdateMcpServerInput,
} from "@/lib/api/capabilities";

export function useMcpServers() {
  return useQuery({ queryKey: mcpServerKeys.all, queryFn: listMcpServers });
}
function useInvalidate() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: mcpServerKeys.all });
}
export function useCreateMcpServer() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (i: CreateMcpServerInput) => createMcpServer(i), onSuccess: invalidate });
}
export function useUpdateMcpServer() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (a: { id: string; input: UpdateMcpServerInput }) => updateMcpServer(a.id, a.input), onSuccess: invalidate });
}
export function useDeleteMcpServer() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (id: string) => deleteMcpServer(id), onSuccess: invalidate });
}
