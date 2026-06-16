import { type ChangeEvent } from "react";
import { Button } from "@/components/ui/Button";
import { attachmentUrl, isImage } from "@/lib/api/attachments";
import { useAttachments } from "./useAttachments";

export function Attachments({ itemId }: { itemId: string }) {
  const { list, upload, remove } = useAttachments(itemId);

  const onPick = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) upload.mutate(file);
    e.target.value = "";
  };

  return (
    <div>
      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-subtle">Attachments</h3>
      <ul className="mb-2 space-y-2">
        {(list.data ?? []).map((att) => (
          <li key={att.id} className="flex items-center gap-2">
            {isImage(att) ? (
              <a href={attachmentUrl(att.id)} target="_blank" rel="noreferrer">
                <img src={attachmentUrl(att.id)} alt={att.filename} className="h-12 w-12 rounded border border-line object-cover" />
              </a>
            ) : (
              <a className="text-sm text-accent hover:underline" href={attachmentUrl(att.id)} target="_blank" rel="noreferrer">
                {att.filename} ({att.size_bytes} B)
              </a>
            )}
            <Button variant="ghost" size="sm" onClick={() => remove.mutate(att.id)}>Delete</Button>
          </li>
        ))}
      </ul>
      <input type="file" aria-label="Upload attachment" onChange={onPick} className="text-xs text-subtle" />
      {upload.isError && <p className="text-sm text-danger">{(upload.error as Error).message}</p>}
    </div>
  );
}
