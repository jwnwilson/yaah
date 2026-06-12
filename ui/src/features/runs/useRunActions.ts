import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  approveRun,
  cancelRun,
  rejectRun,
  runKeys,
  updateRun,
  type UpdateRunInput,
} from "../../lib/api/runs";

export function useRunActions(taskId: string, runId: string) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: runKeys.forTask(taskId) });

  const cancel = useMutation({ mutationFn: () => cancelRun(runId), onSuccess: invalidate });
  const approve = useMutation({ mutationFn: () => approveRun(runId), onSuccess: invalidate });
  const reject = useMutation({ mutationFn: () => rejectRun(runId), onSuccess: invalidate });
  const edit = useMutation({
    mutationFn: (input: UpdateRunInput) => updateRun(runId, input),
    onSuccess: invalidate,
  });
  return { cancel, approve, reject, edit };
}
