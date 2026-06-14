import { useState } from "react";
import type { Secret } from "../../lib/api/types";
import { ResourceTable } from "../components/ResourceTable";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useCreateSecret, useDeleteSecret, useSecrets } from "./useSecrets";
import { SetSecretValueDialog } from "./SetSecretValueDialog";

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
        <h1 className="text-xl font-semibold">Secrets</h1>
        <button onClick={() => setCreating(true)} className="rounded bg-blue-600 px-3 py-1 text-sm text-white">New secret</button>
      </div>
      {isLoading && <p className="text-sm text-gray-500">Loading…</p>}
      {isError && <p className="text-sm text-red-600">{(error as Error).message}</p>}
      <ResourceTable
        rows={data}
        rowKey={(s) => s.id}
        empty="No secrets yet."
        columns={[
          { header: "Name", render: (s) => <span className="font-medium">{s.name}</span> },
          { header: "Description", render: (s) => <span className="text-gray-600">{s.description}</span> },
          { header: "Status", render: (s) => (s.has_value ? <span className="text-green-700">● configured</span> : <span className="text-gray-400">○ empty</span>) },
        ]}
        actions={(s) => (
          <div className="flex justify-end gap-2 text-sm">
            <button onClick={() => setValueFor(s)} className="text-blue-700">Set value</button>
            <button onClick={() => setDeleting(s)} className="text-red-600">Delete</button>
          </div>
        )}
      />

      {creating && (
        <div className="fixed inset-0 grid place-items-center bg-black/30">
          <form onSubmit={submitCreate} className="w-96 space-y-3 rounded bg-white p-4 shadow">
            <h2 className="text-lg font-semibold">New secret</h2>
            <label className="block text-sm">Name<input className="mt-1 w-full rounded border p-2" value={name} onChange={(e) => setName(e.target.value)} /></label>
            <label className="block text-sm">Description<input className="mt-1 w-full rounded border p-2" value={description} onChange={(e) => setDescription(e.target.value)} /></label>
            {create.isError && <p className="text-xs text-red-600">{(create.error as Error).message}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setCreating(false)} className="rounded px-3 py-1 text-sm">Cancel</button>
              <button type="submit" disabled={name.trim() === "" || create.isPending} className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50">Create</button>
            </div>
          </form>
        </div>
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
