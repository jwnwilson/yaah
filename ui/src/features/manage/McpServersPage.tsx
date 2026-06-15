import { useState } from "react";
import type { McpServer, McpTransport } from "@/lib/api/types";
import { Button } from "@/ui/Button";
import { ConfirmDialog } from "@/ui/ConfirmDialog";
import { Dialog } from "@/ui/Dialog";
import { Field, Input, Select } from "@/ui/Field";
import { ResourceTable } from "@/ui/ResourceTable";
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
        <h1 className="text-xl font-semibold text-fg">MCP servers</h1>
        <Button size="sm" onClick={openNew}>New MCP server</Button>
      </div>
      {isLoading && <p className="text-sm text-subtle">Loading…</p>}
      {isError && <p className="text-sm text-danger">{(error as Error).message}</p>}
      <ResourceTable
        rows={data}
        rowKey={(s) => s.id}
        empty="No MCP servers yet."
        columns={[
          { header: "Name", render: (s) => <span className="font-medium">{s.name}</span> },
          { header: "Transport", render: (s) => <span className="text-muted">{s.transport}</span> },
          { header: "Command / URL", render: (s) => <span className="text-muted">{s.command_or_url}</span> },
          { header: "Tools", render: (s) => <span className="text-muted">{s.tool_allowlist.length}</span> },
        ]}
        actions={(s) => (
          <div className="flex justify-end gap-3 text-sm">
            <button onClick={() => openEdit(s)} className="text-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded">Edit</button>
            <button onClick={() => setDeleting(s)} className="text-danger hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded">Delete</button>
          </div>
        )}
      />

      {editing && (
        <Dialog title={editing === "new" ? "New MCP server" : "Edit MCP server"} onClose={() => setEditing(null)}>
          <form onSubmit={submit} className="space-y-3">
            <Field label="Name"><Input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></Field>
            <Field label="Transport">
              <Select value={draft.transport} onChange={(e) => setDraft({ ...draft, transport: e.target.value as McpTransport })}>
                <option value="stdio">stdio</option>
                <option value="http">http</option>
              </Select>
            </Field>
            <Field label="Command or URL"><Input value={draft.command_or_url} onChange={(e) => setDraft({ ...draft, command_or_url: e.target.value })} /></Field>
            <Field label="Add tool">
              <Input placeholder="mcp__server__tool (Enter to add)" value={tool} onChange={(e) => setTool(e.target.value)} onKeyDown={addTool} />
            </Field>
            <div className="flex flex-wrap gap-1">
              {draft.tool_allowlist.map((t) => (
                <span key={t} className="flex items-center gap-1 rounded-full bg-surface-hover px-2 py-0.5 text-xs text-muted">
                  {t}
                  <button type="button" aria-label={`remove ${t}`} onClick={() => removeTool(t)} className="text-subtle hover:text-fg">✕</button>
                </span>
              ))}
            </div>
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
