import { useEffect, useState } from "react";
import type { Agent } from "../../lib/api/agents";
import { ResourceTable } from "../components/ResourceTable";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { Field, Input } from "../../ui/Field";
import { useAgents, useTeams, useUpdateAgent } from "./useAgents";

interface Draft { model_alias: string; allowed_tools: string }

export function ModelsPage() {
  const teams = useTeams();
  const [teamId, setTeamId] = useState<string | undefined>(undefined);
  useEffect(() => {
    if (!teamId && teams.data && teams.data.length > 0) setTeamId(teams.data[0].id);
  }, [teams.data, teamId]);

  const agents = useAgents(teamId);
  const update = useUpdateAgent(teamId ?? "");
  const [editing, setEditing] = useState<Agent | null>(null);
  const [draft, setDraft] = useState<Draft>({ model_alias: "", allowed_tools: "" });

  function openEdit(a: Agent) {
    setDraft({ model_alias: a.model_alias, allowed_tools: a.allowed_tools.join(", ") });
    setEditing(a);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!editing) return;
    await update.mutateAsync({
      id: editing.id,
      input: {
        model_alias: draft.model_alias,
        allowed_tools: draft.allowed_tools.split(",").map((t) => t.trim()).filter(Boolean),
      },
    });
    setEditing(null);
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-fg">Models</h1>
        {teams.data && teams.data.length > 0 && (
          <label className="text-sm">
            Team{" "}
            <select className="rounded-md border border-line bg-surface px-2 py-1 text-sm text-fg" value={teamId ?? ""}
              onChange={(e) => setTeamId(e.target.value)}>
              {teams.data.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </label>
        )}
      </div>
      {agents.isLoading && <p className="text-sm text-subtle">Loading…</p>}
      {agents.isError && <p className="text-sm text-danger">{(agents.error as Error).message}</p>}
      <ResourceTable
        rows={agents.data ?? []}
        rowKey={(a) => a.id}
        empty="No agents in this team."
        columns={[
          { header: "Role", render: (a) => <span className="text-muted">{a.role}</span> },
          { header: "Name", render: (a) => <span className="font-medium">{a.name}</span> },
          { header: "Model", render: (a) => <span className="font-mono text-xs">{a.model_alias}</span> },
          { header: "Runtime", render: (a) => <span className="text-muted">{a.runtime}</span> },
        ]}
        actions={(a) => (
          <button onClick={() => openEdit(a)} className="text-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded">Edit</button>
        )}
      />

      {editing && (
        <Dialog title={`Edit ${editing.name}`} onClose={() => setEditing(null)}>
          <form onSubmit={submit} className="space-y-3">
            <Field label="Model alias">
              <Input value={draft.model_alias}
                onChange={(e) => setDraft({ ...draft, model_alias: e.target.value })} />
            </Field>
            <Field label="Allowed tools (comma-separated)">
              <Input value={draft.allowed_tools}
                onChange={(e) => setDraft({ ...draft, allowed_tools: e.target.value })} />
            </Field>
            {update.isError && <p className="text-xs text-danger">{(update.error as Error).message}</p>}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(null)}>Cancel</Button>
              <Button type="submit" size="sm" loading={update.isPending}>Save</Button>
            </div>
          </form>
        </Dialog>
      )}
    </div>
  );
}
