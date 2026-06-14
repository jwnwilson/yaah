import { useState } from "react";
import type { McpServer, McpTransport } from "../../lib/api/types";
import { ResourceTable } from "../components/ResourceTable";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useCreateMcpServer, useDeleteMcpServer, useMcpServers, useUpdateMcpServer } from "./useMcpServers";

interface Draft { name: string; transport: McpTransport; command_or_url: string; tool_allowlist: string[] }
const EMPTY: Draft = { name: "", transport: "stdio", command_or_url: "", tool_allowlist: [] };

export function McpServersPage() {
  const { data = [], isLoading, isError, error } = useMcpServers();
  const create = useCreateMcpServer();
  const update = useUpdateMcpServer();
  const del = useDeleteMcpServer();
  const [editing, setEditing] = useState<McpServer | "new" | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [tool, setTool] = useState("");
  const [deleting, setDeleting] = useState<McpServer | null>(null);

  function openNew() { setDraft(EMPTY); setTool(""); setEditing("new"); }
  function openEdit(s: McpServer) {
    setDraft({ name: s.name, transport: s.transport, command_or_url: s.command_or_url, tool_allowlist: [...s.tool_allowlist] });
    setTool(""); setEditing(s);
  }
  function addTool(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key !== "Enter") return;
    e.preventDefault();
    const t = tool.trim();
    if (t && !draft.tool_allowlist.includes(t)) setDraft({ ...draft, tool_allowlist: [...draft.tool_allowlist, t] });
    setTool("");
  }
  function removeTool(t: string) { setDraft({ ...draft, tool_allowlist: draft.tool_allowlist.filter((x) => x !== t) }); }

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
        <h1 className="text-xl font-semibold">MCP servers</h1>
        <button onClick={openNew} className="rounded bg-blue-600 px-3 py-1 text-sm text-white">New MCP server</button>
      </div>
      {isLoading && <p className="text-sm text-gray-500">Loading…</p>}
      {isError && <p className="text-sm text-red-600">{(error as Error).message}</p>}
      <ResourceTable
        rows={data}
        rowKey={(s) => s.id}
        empty="No MCP servers yet."
        columns={[
          { header: "Name", render: (s) => <span className="font-medium">{s.name}</span> },
          { header: "Transport", render: (s) => <span className="text-gray-600">{s.transport}</span> },
          { header: "Command / URL", render: (s) => <span className="text-gray-600">{s.command_or_url}</span> },
          { header: "Tools", render: (s) => <span className="text-gray-600">{s.tool_allowlist.length}</span> },
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
          <form onSubmit={submit} className="w-[28rem] space-y-3 rounded bg-white p-4 shadow">
            <h2 className="text-lg font-semibold">{editing === "new" ? "New MCP server" : "Edit MCP server"}</h2>
            <label className="block text-sm">Name<input className="mt-1 w-full rounded border p-2" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></label>
            <label className="block text-sm">Transport
              <select className="mt-1 w-full rounded border p-2" value={draft.transport} onChange={(e) => setDraft({ ...draft, transport: e.target.value as McpTransport })}>
                <option value="stdio">stdio</option>
                <option value="http">http</option>
              </select>
            </label>
            <label className="block text-sm">Command or URL<input className="mt-1 w-full rounded border p-2" value={draft.command_or_url} onChange={(e) => setDraft({ ...draft, command_or_url: e.target.value })} /></label>
            <label className="block text-sm">Add tool
              <input className="mt-1 w-full rounded border p-2" placeholder="mcp__server__tool (Enter to add)" value={tool} onChange={(e) => setTool(e.target.value)} onKeyDown={addTool} />
            </label>
            <div className="flex flex-wrap gap-1">
              {draft.tool_allowlist.map((t) => (
                <span key={t} className="flex items-center gap-1 rounded bg-gray-100 px-2 py-0.5 text-xs">
                  {t}
                  <button type="button" aria-label={`remove ${t}`} onClick={() => removeTool(t)} className="text-gray-500">✕</button>
                </span>
              ))}
            </div>
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
          title="Delete MCP server"
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
