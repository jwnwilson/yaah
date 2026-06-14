import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createSecret, deleteSecret, listSecrets, secretKeys, setSecretValue, updateSecret,
  type CreateSecretInput, type UpdateSecretInput,
} from "../../lib/api/capabilities";

export function useSecrets() {
  return useQuery({ queryKey: secretKeys.all, queryFn: listSecrets });
}
function useInvalidate() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: secretKeys.all });
}
export function useCreateSecret() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (i: CreateSecretInput) => createSecret(i), onSuccess: invalidate });
}
export function useUpdateSecret() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (a: { id: string; input: UpdateSecretInput }) => updateSecret(a.id, a.input), onSuccess: invalidate });
}
export function useSetSecretValue() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (a: { id: string; value: string }) => setSecretValue(a.id, a.value), onSuccess: invalidate });
}
export function useDeleteSecret() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (id: string) => deleteSecret(id), onSuccess: invalidate });
}
