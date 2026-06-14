import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";

interface ConfirmDialogProps {
  title: string;
  message: string;
  confirmLabel?: string;
  pending?: boolean;
  error?: string;
  onConfirm: () => void | Promise<void>;
  onClose: () => void;
}

export function ConfirmDialog({ title, message, confirmLabel = "Delete", pending, error, onConfirm, onClose }: ConfirmDialogProps) {
  return (
    <Dialog title={title} onClose={onClose}>
      <div className="space-y-3">
        <p className="text-sm text-muted">{message}</p>
        {error && <p className="text-xs text-danger">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button type="button" variant="danger" size="sm" loading={pending} onClick={() => void onConfirm()}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
