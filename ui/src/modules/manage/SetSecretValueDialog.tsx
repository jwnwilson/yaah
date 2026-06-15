import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Field, Input } from "@/components/ui/Field";
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
    <Dialog title={`Set secret — ${secretName}`} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <Field label="Value">
          <Input type="password" autoComplete="off" value={value} onChange={(e) => setValue(e.target.value)} />
        </Field>
        <p className="text-xs text-subtle">The value is write-only — it is stored encrypted and never shown again.</p>
        {setVal.isError && (
          <p className="text-xs text-danger">
            {is503 ? "Secret encryption key not configured on the server." : (setVal.error as Error).message}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button type="submit" size="sm" disabled={value === ""} loading={setVal.isPending}>Save</Button>
        </div>
      </form>
    </Dialog>
  );
}
