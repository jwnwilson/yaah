import { useState } from "react";
import { initials, roleVisual } from "@/modules/team/roleVisual";
import { useTeamRoster } from "@/modules/team/useTeamRoster";
import { useMarkRead, useMessages, useSendMessage } from "./useInbox";

function Avatar({ color, text }: { color: string; text: string }) {
  return (
    <span
      className="flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold text-white"
      style={{ backgroundColor: color }}
      aria-hidden
    >
      {text}
    </span>
  );
}

export function InboxPage() {
  const { agents } = useTeamRoster();
  const [box, setBox] = useState("me");
  const messages = useMessages(box);
  const markRead = useMarkRead(box);
  const send = useSendMessage(box);
  const [draft, setDraft] = useState("");

  const agentList = agents.data ?? [];
  const agentById = new Map(agentList.map((a) => [a.id, a]));

  async function onSend(e: React.FormEvent) {
    e.preventDefault();
    if (!draft.trim() || box === "me") return;
    await send.mutateAsync({
      recipient_kind: "agent",
      recipient_agent_id: box,
      body: draft.trim(),
    });
    setDraft("");
  }

  const mailboxBtn = (active: boolean) =>
    `flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm ${
      active ? "bg-accent/10 font-medium text-fg" : "text-muted hover:text-fg"
    }`;

  return (
    <div className="flex h-full">
      <aside className="w-56 shrink-0 overflow-auto border-r border-line p-3">
        <h1 className="mb-2 text-sm font-semibold text-fg">Inbox</h1>
        <button className={mailboxBtn(box === "me")} onClick={() => setBox("me")}>
          <Avatar color="#64748b" text="You" />
          <span>Notices</span>
        </button>
        {agentList.map((a) => (
          <button key={a.id} className={mailboxBtn(box === a.id)} onClick={() => setBox(a.id)}>
            <Avatar color={roleVisual(a.role).color} text={initials(a.name)} />
            <span className="truncate">{a.name}</span>
          </button>
        ))}
      </aside>

      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 space-y-2 overflow-auto p-4">
          {messages.data?.length === 0 && (
            <p className="text-sm text-muted">No messages in this mailbox.</p>
          )}
          {messages.data?.map((m) => {
            const sender = m.sender_agent_id ? agentById.get(m.sender_agent_id) : undefined;
            const color = sender ? roleVisual(sender.role).color : "#64748b";
            const label = sender ? sender.name : m.sender_kind;
            const unread = m.read_at === null;
            return (
              <button
                key={m.id}
                onClick={() => unread && markRead.mutate(m.id)}
                className={`block w-full rounded-md border border-line p-3 text-left ${
                  unread ? "bg-surface" : "bg-canvas"
                }`}
              >
                <div className="flex items-center gap-2">
                  <Avatar color={color} text={sender ? initials(sender.name) : "•"} />
                  <span className="text-xs font-medium text-fg">{label}</span>
                  {unread && <span className="ml-auto h-2 w-2 rounded-full bg-accent" />}
                </div>
                {m.subject && <div className="mt-1 text-sm font-medium text-fg">{m.subject}</div>}
                <div className="mt-1 text-sm text-muted">{m.body}</div>
              </button>
            );
          })}
        </div>
        {box !== "me" && (
          <form onSubmit={onSend} className="flex gap-2 border-t border-line p-3">
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Message this agent…"
              aria-label="Message body"
              className="flex-1 rounded-md border border-line bg-surface px-2 py-1 text-sm text-fg"
            />
            <button
              type="submit"
              className="rounded-md bg-accent px-3 py-1 text-sm font-medium text-white"
            >
              Send
            </button>
          </form>
        )}
      </section>
    </div>
  );
}
