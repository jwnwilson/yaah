import { useState } from "react";
import { useSetSecretValue } from "./useSecrets";

export function SetSecretValueDialog({ secretId, secretName, onClose }: { secretId: string; secretName: string; onClose: () => void }) {
  const [value, setValue] = useState("");
  const setVal = useSetSecretValue();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (value === "") return;
    try {
      await setVal.mutateAsync({ id: secretId, value });
      setValue("");
      onClose();
    } catch {
      setValue("");
    }
  }

  const is503 = (setVal.error as { status?: number } | null)?.status === 503;

  return (
    <div className="fixed inset-0 grid place-items-center bg-black/30">
      <form onSubmit={submit} className="w-96 space-y-3 rounded bg-white p-4 shadow">
        <h2 className="text-lg font-semibold">Set value — {secretName}</h2>
        <label className="block text-sm">
          Value
          <input type="password" autoComplete="off" className="mt-1 w-full rounded border p-2" value={value} onChange={(e) => setValue(e.target.value)} />
        </label>
        <p className="text-xs text-gray-500">The value is write-only — it is stored encrypted and never shown again.</p>
        {setVal.isError && (
          <p className="text-xs text-red-600">
            {is503 ? "Secret encryption key not configured on the server." : (setVal.error as Error).message}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded px-3 py-1 text-sm">Cancel</button>
          <button type="submit" disabled={value === "" || setVal.isPending} className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50">Save</button>
        </div>
      </form>
    </div>
  );
}
