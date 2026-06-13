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
    <div className="fixed inset-0 grid place-items-center bg-black/30">
      <div className="w-96 space-y-3 rounded bg-white p-4 shadow">
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="text-sm text-gray-600">{message}</p>
        {error && <p className="text-xs text-red-600">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded px-3 py-1 text-sm">Cancel</button>
          <button
            type="button"
            disabled={pending}
            onClick={() => void onConfirm()}
            className="rounded bg-red-600 px-3 py-1 text-sm text-white disabled:opacity-50"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
