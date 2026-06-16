import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  attachmentKeys,
  deleteAttachment,
  getAttachments,
  uploadAttachment,
} from "@/lib/api/attachments";

export function useAttachments(itemId: string) {
  const qc = useQueryClient();
  const list = useQuery({
    queryKey: attachmentKeys.forItem(itemId),
    queryFn: () => getAttachments(itemId),
  });
  const invalidate = () =>
    qc.invalidateQueries({ queryKey: attachmentKeys.forItem(itemId) });

  const upload = useMutation({
    mutationFn: (file: File) => uploadAttachment(itemId, file),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: (attachmentId: string) => deleteAttachment(attachmentId),
    onSuccess: invalidate,
  });
  return { list, upload, remove };
}
