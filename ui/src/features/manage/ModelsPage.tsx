import { useEffect, useState } from "react";
import type { Agent } from "../../lib/api/agents";
import { ResourceTable } from "../components/ResourceTable";
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
        <h1 className="text-xl font-semibold">Models</h1>
        {teams.data && teams.data.length > 0 && (
          <label className="text-sm">
            Team{" "}
            <select className="rounded border p-1" value={teamId ?? ""}
              onChange={(e) => setTeamId(e.target.value)}>
              {teams.data.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </label>
        )}
      </div>
      {agents.isLoading && <p className="text-sm text-gray-500">Loading…</p>}
      {agents.isError && <p className="text-sm text-red-600">{(agents.error as Error).message}</p>}
      <ResourceTable
        rows={agents.data ?? []}
        rowKey={(a) => a.id}
        empty="No agents in this team."
        columns={[
          { header: "Role", render: (a) => <span className="text-gray-600">{a.role}</span> },
          { header: "Name", render: (a) => <span className="font-medium">{a.name}</span> },
          { header: "Model", render: (a) => <span className="font-mono text-xs">{a.model_alias}</span> },
          { header: "Runtime", render: (a) => <span className="text-gray-600">{a.runtime}</span> },
        ]}
        actions={(a) => (
          <button onClick={() => openEdit(a)} className="text-sm text-blue-700">Edit</button>
        )}
      />

      {editing && (
        <div className="fixed inset-0 grid place-items-center bg-black/30">
          <form onSubmit={submit} className="w-96 space-y-3 rounded bg-white p-4 shadow">
            <h2 className="text-lg font-semibold">Edit {editing.name}</h2>
            <label className="block text-sm">Model alias
              <input className="mt-1 w-full rounded border p-2" value={draft.model_alias}
                onChange={(e) => setDraft({ ...draft, model_alias: e.target.value })} />
            </label>
            <label className="block text-sm">Allowed tools (comma-separated)
              <input className="mt-1 w-full rounded border p-2" value={draft.allowed_tools}
                onChange={(e) => setDraft({ ...draft, allowed_tools: e.target.value })} />
            </label>
            {update.isError && <p className="text-xs text-red-600">{(update.error as Error).message}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setEditing(null)} className="rounded px-3 py-1 text-sm">Cancel</button>
              <button type="submit" disabled={update.isPending}
                className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50">Save</button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
