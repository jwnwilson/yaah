import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { Message } from "@/lib/api/messages";
import { useMessages } from "@/modules/inbox/useInbox";
import { initials, roleVisual } from "./roleVisual";
import { useAgent, useSentMessages } from "./useAgentDetail";

function MessageList({ data, empty }: { data: Message[] | undefined; empty: string }) {
  if (!data || data.length === 0) return <p className="text-sm text-muted">{empty}</p>;
  return (
    <ul className="space-y-2">
      {data.map((m) => (
        <li key={m.id} className="rounded-md border border-line bg-surface p-3">
          <div className="mb-1 flex items-center gap-2 text-xs text-muted">
            <span className="rounded bg-canvas px-1.5 py-0.5">{m.kind}</span>
            {m.run_id && <span>run {m.run_id.slice(0, 8)}</span>}
          </div>
          {m.subject && <div className="text-sm font-medium text-fg">{m.subject}</div>}
          <div className="text-sm text-muted">{m.body}</div>
        </li>
      ))}
    </ul>
  );
}

export function AgentDetailPage() {
  const { agentId } = useParams();
  const id = agentId ?? "";
  const agent = useAgent(id);
  const sent = useSentMessages(id);
  const inbox = useMessages(id);
  const [tab, setTab] = useState<"output" | "inbox">("output");

  if (agent.isLoading) return <div className="p-6 text-muted">Loading…</div>;
  if (!agent.data) return <div className="p-6 text-muted">Agent not found.</div>;

  const a = agent.data;
  const v = roleVisual(a.role);
  const tabClass = (active: boolean) =>
    `border-b-2 px-3 py-1.5 text-sm ${active ? "border-accent font-medium text-fg" : "border-transparent text-muted hover:text-fg"}`;

  return (
    <div className="p-6">
      <Link to="/team" className="text-sm text-muted hover:text-fg">← Team</Link>
      <header className="mt-2 flex items-center gap-3">
        <span
          className="flex h-12 w-12 items-center justify-center rounded-full text-base font-semibold text-white"
          style={{ backgroundColor: v.color }}
          aria-hidden
        >
          {initials(a.name)}
        </span>
        <div>
          <h1 className="text-xl font-semibold text-fg">{a.name}</h1>
          <div className="text-sm text-muted">{v.label} · {a.model_alias}</div>
        </div>
        <Link to="/manage/agents" className="ml-auto text-sm text-accent hover:underline">
          Edit in Manage →
        </Link>
      </header>
      {a.purpose && <p className="mt-3 text-sm text-fg">{a.purpose}</p>}

      <div className="mt-5 flex gap-1 border-b border-line">
        <button className={tabClass(tab === "output")} onClick={() => setTab("output")}>Output</button>
        <button className={tabClass(tab === "inbox")} onClick={() => setTab("inbox")}>Inbox</button>
      </div>
      <div className="mt-4">
        {tab === "output" ? (
          <MessageList data={sent.data} empty="No output yet — this agent has not sent anything." />
        ) : (
          <MessageList data={inbox.data} empty="No messages in this agent's inbox." />
        )}
      </div>
    </div>
  );
}
