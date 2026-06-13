import { useState } from "react";
import { useChat } from "./useChat";

interface ChatRailProps {
  projectId: string;
}

export function ChatRail({ projectId }: ChatRailProps) {
  const { turns, send } = useChat(projectId);
  const [text, setText] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed) return;
    send.mutate(trimmed);
    setText("");
  };

  return (
    <aside className="flex h-full w-80 shrink-0 flex-col border-l">
      <h2 className="border-b p-2 text-sm font-semibold">Team lead</h2>
      <div className="flex-1 space-y-2 overflow-y-auto p-2 text-sm">
        {turns.map((t, i) => (
          <div key={i} className={t.role === "user" ? "text-right" : ""}>
            <span className="inline-block rounded bg-gray-100 px-2 py-1">
              {t.content}
            </span>
          </div>
        ))}
      </div>
      <form className="flex gap-1 border-t p-2" onSubmit={handleSubmit}>
        <input
          className="flex-1 rounded border p-1 text-sm"
          placeholder="Message the team lead…"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <button
          type="submit"
          className="rounded bg-blue-600 px-3 py-1 text-sm text-white"
          disabled={send.isPending}
        >
          Send
        </button>
      </form>
    </aside>
  );
}
