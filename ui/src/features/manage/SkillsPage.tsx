import { useState } from "react";
import type { Skill } from "../../lib/api/types";
import { ResourceTable } from "../components/ResourceTable";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useCreateSkill, useDeleteSkill, useSkills, useUpdateSkill } from "./useSkills";

interface Draft { name: string; description: string; source: string }
const EMPTY: Draft = { name: "", description: "", source: "" };

export function SkillsPage() {
  const { data = [], isLoading, isError, error } = useSkills();
  const create = useCreateSkill();
  const update = useUpdateSkill();
  const del = useDeleteSkill();
  const [editing, setEditing] = useState<Skill | "new" | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [deleting, setDeleting] = useState<Skill | null>(null);

  function openNew() { setDraft(EMPTY); setEditing("new"); }
  function openEdit(s: Skill) { setDraft({ name: s.name, description: s.description, source: s.source }); setEditing(s); }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (draft.name.trim() === "") return;
    if (editing === "new") await create.mutateAsync(draft);
    else if (editing) await update.mutateAsync({ id: editing.id, input: draft });
    setEditing(null);
  }

  const mutating = create.isPending || update.isPending;
  const mutError = (create.error || update.error) as Error | null;

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Skills</h1>
        <button onClick={openNew} className="rounded bg-blue-600 px-3 py-1 text-sm text-white">New skill</button>
      </div>
      {isLoading && <p className="text-sm text-gray-500">Loading…</p>}
      {isError && <p className="text-sm text-red-600">{(error as Error).message}</p>}
      <ResourceTable
        rows={data}
        rowKey={(s) => s.id}
        empty="No skills yet."
        columns={[
          { header: "Name", render: (s) => <span className="font-medium">{s.name}</span> },
          { header: "Description", render: (s) => <span className="text-gray-600">{s.description}</span> },
          { header: "Source", render: (s) => <span className="text-gray-600">{s.source}</span> },
        ]}
        actions={(s) => (
          <div className="flex justify-end gap-2 text-sm">
            <button onClick={() => openEdit(s)} className="text-blue-700">Edit</button>
            <button onClick={() => setDeleting(s)} className="text-red-600">Delete</button>
          </div>
        )}
      />

      {editing && (
        <div className="fixed inset-0 grid place-items-center bg-black/30">
          <form onSubmit={submit} className="w-96 space-y-3 rounded bg-white p-4 shadow">
            <h2 className="text-lg font-semibold">{editing === "new" ? "New skill" : "Edit skill"}</h2>
            <label className="block text-sm">Name<input className="mt-1 w-full rounded border p-2" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></label>
            <label className="block text-sm">Description<input className="mt-1 w-full rounded border p-2" value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></label>
            <label className="block text-sm">Source<input className="mt-1 w-full rounded border p-2" value={draft.source} onChange={(e) => setDraft({ ...draft, source: e.target.value })} /></label>
            {mutError && <p className="text-xs text-red-600">{mutError.message}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setEditing(null)} className="rounded px-3 py-1 text-sm">Cancel</button>
              <button type="submit" disabled={draft.name.trim() === "" || mutating} className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50">{editing === "new" ? "Create" : "Save"}</button>
            </div>
          </form>
        </div>
      )}

      {deleting && (
        <ConfirmDialog
          title="Delete skill"
          message={`Delete "${deleting.name}"?`}
          pending={del.isPending}
          error={del.isError ? (del.error as Error).message : undefined}
          onConfirm={async () => { await del.mutateAsync(deleting.id); setDeleting(null); }}
          onClose={() => setDeleting(null)}
        />
      )}
    </div>
  );
}
