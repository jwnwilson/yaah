import { useState } from "react";
import { ConfirmDialog } from "@/features/components/ConfirmDialog";
import { ResourceTable } from "@/features/components/ResourceTable";
import type { Secret } from "@/lib/api/types";
import { Button } from "@/ui/Button";
import { Dialog } from "@/ui/Dialog";
import { Field, Input } from "@/ui/Field";
import { SetSecretValueDialog } from "./SetSecretValueDialog";
import { useCreateSecret, useDeleteSecret, useSecrets } from "./useSecrets";

export function SecretsPage() {
  const { data = [], isLoading, isError, error } = useSecrets();
  const create = useCreateSecret();
  const del = useDeleteSecret();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [valueFor, setValueFor] = useState<Secret | null>(null);
  const [deleting, setDeleting] = useState<Secret | null>(null);

  async function submitCreate(e: React.FormEvent) {
    e.preventDefault();
    if (name.trim() === "") return;
    await create.mutateAsync({ name: name.trim(), description: description.trim() });
    setName(""); setDescription(""); setCreating(false);
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-fg">Secrets</h1>
        <Button size="sm" onClick={() => setCreating(true)}>New secret</Button>
      </div>
      {isLoading && <p className="text-sm text-subtle">Loading…</p>}
      {isError && <p className="text-sm text-danger">{(error as Error).message}</p>}
      <ResourceTable
        rows={data}
        rowKey={(s) => s.id}
        empty="No secrets yet."
        columns={[
          { header: "Name", render: (s) => <span className="font-medium">{s.name}</span> },
          { header: "Description", render: (s) => <span className="text-muted">{s.description}</span> },
          { header: "Status", render: (s) => (s.has_value ? <span className="text-success">● configured</span> : <span className="text-subtle">○ empty</span>) },
        ]}
        actions={(s) => (
          <div className="flex justify-end gap-3 text-sm">
            <button onClick={() => setValueFor(s)} className="text-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded">Set value</button>
            <button onClick={() => setDeleting(s)} className="text-danger hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded">Delete</button>
          </div>
        )}
      />

      {creating && (
        <Dialog title="New secret" onClose={() => setCreating(false)}>
          <form onSubmit={submitCreate} className="space-y-3">
            <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
            <Field label="Description"><Input value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
            {create.isError && <p className="text-xs text-danger">{(create.error as Error).message}</p>}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" size="sm" onClick={() => setCreating(false)}>Cancel</Button>
              <Button type="submit" size="sm" disabled={name.trim() === ""} loading={create.isPending}>Create</Button>
            </div>
          </form>
        </Dialog>
      )}

      {valueFor && <SetSecretValueDialog secretId={valueFor.id} secretName={valueFor.name} onClose={() => setValueFor(null)} />}

      {deleting && (
        <ConfirmDialog
          title="Delete secret"
          message={`Delete "${deleting.name}"? This cannot be undone.`}
          pending={del.isPending}
          error={del.isError ? (del.error as Error).message : undefined}
          onConfirm={async () => { await del.mutateAsync(deleting.id); setDeleting(null); }}
          onClose={() => setDeleting(null)}
        />
      )}
    </div>
  );
}
