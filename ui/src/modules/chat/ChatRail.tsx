import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Field";
import { useChat } from "./useChat";

interface ChatRailProps {
  projectId: string;
  epicId?: string;
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
    <aside className="flex h-full w-80 shrink-0 flex-col border-l border-line bg-panel">
      <h2 className="border-b border-line p-2 text-sm font-semibold text-fg">Team lead</h2>
      <div className="flex-1 space-y-2 overflow-y-auto p-2 text-sm">
        {turns.map((t, i) => (
          <div key={i} className={t.role === "user" ? "text-right" : ""}>
            <span
              className={`inline-block rounded-lg px-2 py-1 ${
                t.role === "user" ? "bg-accent text-accent-fg" : "bg-surface text-fg"
              }`}
            >
              {t.content}
            </span>
          </div>
        ))}
      </div>
      <form className="flex gap-1 border-t border-line p-2" onSubmit={handleSubmit}>
        <Input
          placeholder="Message the team lead…"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <Button type="submit" size="sm" loading={send.isPending}>Send</Button>
      </form>
    </aside>
  );
}
