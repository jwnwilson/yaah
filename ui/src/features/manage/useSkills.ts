import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createSkill, deleteSkill, listSkills, skillKeys, updateSkill,
  type CreateSkillInput, type UpdateSkillInput,
} from "../../lib/api/capabilities";

export function useSkills() {
  return useQuery({ queryKey: skillKeys.all, queryFn: listSkills });
}
function useInvalidate() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: skillKeys.all });
}
export function useCreateSkill() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (i: CreateSkillInput) => createSkill(i), onSuccess: invalidate });
}
export function useUpdateSkill() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (a: { id: string; input: UpdateSkillInput }) => updateSkill(a.id, a.input), onSuccess: invalidate });
}
export function useDeleteSkill() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (id: string) => deleteSkill(id), onSuccess: invalidate });
}
