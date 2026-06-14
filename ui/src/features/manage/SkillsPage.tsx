import { useState } from "react";
import type { Skill } from "../../lib/api/types";
import { ResourceTable } from "../components/ResourceTable";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { Field, Input } from "../../ui/Field";
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
        <h1 className="text-xl font-semibold text-fg">Skills</h1>
        <Button size="sm" onClick={openNew}>New skill</Button>
      </div>
      {isLoading && <p className="text-sm text-subtle">Loading…</p>}
      {isError && <p className="text-sm text-danger">{(error as Error).message}</p>}
      <ResourceTable
        rows={data}
        rowKey={(s) => s.id}
        empty="No skills yet."
        columns={[
          { header: "Name", render: (s) => <span className="font-medium">{s.name}</span> },
          { header: "Description", render: (s) => <span className="text-muted">{s.description}</span> },
          { header: "Source", render: (s) => <span className="text-muted">{s.source}</span> },
        ]}
        actions={(s) => (
          <div className="flex justify-end gap-3 text-sm">
            <button onClick={() => openEdit(s)} className="text-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded">Edit</button>
            <button onClick={() => setDeleting(s)} className="text-danger hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded">Delete</button>
          </div>
        )}
      />

      {editing && (
        <Dialog title={editing === "new" ? "New skill" : "Edit skill"} onClose={() => setEditing(null)}>
          <form onSubmit={submit} className="space-y-3">
            <Field label="Name"><Input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></Field>
            <Field label="Description"><Input value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></Field>
            <Field label="Source"><Input value={draft.source} onChange={(e) => setDraft({ ...draft, source: e.target.value })} /></Field>
            {mutError && <p className="text-xs text-danger">{mutError.message}</p>}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(null)}>Cancel</Button>
              <Button type="submit" size="sm" disabled={draft.name.trim() === ""} loading={mutating}>
                {editing === "new" ? "Create" : "Save"}
              </Button>
            </div>
          </form>
        </Dialog>
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
