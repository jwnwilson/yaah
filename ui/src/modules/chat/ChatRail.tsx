import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Field";
import { IconButton } from "@/components/ui/IconButton";
import { useChat } from "./useChat";
import { useSpeechDictation } from "./useSpeechDictation";

interface ChatRailProps {
  projectId: string;
  epicId?: string;
  autoDictate?: boolean;
  onDictateConsumed?: () => void;
  onListeningChange?: (listening: boolean) => void;
}

export function ChatRail({
  projectId,
  epicId,
  autoDictate,
  onDictateConsumed,
  onListeningChange,
}: ChatRailProps) {
  const {
    turns,
    send,
    proposedEpicUpdate,
    acceptEpicUpdate,
    dismissEpicUpdate,
    proposedUpdates,
    applyUpdate,
    dismissUpdate,
  } = useChat(projectId, epicId);
  const [text, setText] = useState("");
  const dictation = useSpeechDictation({
    onTranscript: (t) => setText((prev) => (prev ? prev + " " : "") + t),
  });

  useEffect(() => {
    if (autoDictate && dictation.supported && !dictation.listening) {
      dictation.start();
      onDictateConsumed?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoDictate]);

  // Surface the dictation listening state to the launcher (drives the global mic indicator),
  // and clear it when the chat closes/unmounts.
  useEffect(() => {
    onListeningChange?.(dictation.listening);
  }, [dictation.listening, onListeningChange]);
  useEffect(() => () => onListeningChange?.(false), [onListeningChange]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed) return;
    send.mutate(trimmed);
    setText("");
  };

  return (
    <aside className="flex h-full w-80 shrink-0 flex-col border-l border-line bg-panel">
      <h2 className="border-b border-line p-2 text-sm font-semibold text-fg">
        {epicId ? "Team lead — focused on epic" : "Team lead"}
      </h2>
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
        {proposedEpicUpdate && (
          <div className="rounded-md border border-line bg-surface p-2">
            <p className="mb-1 text-xs font-semibold text-fg">Suggested epic spec</p>
            {proposedEpicUpdate.body && (
              <p className="mb-1 text-xs text-muted">{proposedEpicUpdate.body}</p>
            )}
            {proposedEpicUpdate.acceptance_criteria?.length ? (
              <ul className="mb-2 list-disc pl-4 text-xs text-muted">
                {proposedEpicUpdate.acceptance_criteria.map((ac, i) => (
                  <li key={i}>{ac}</li>
                ))}
              </ul>
            ) : null}
            <div className="flex gap-2">
              <Button size="sm" loading={acceptEpicUpdate.isPending} onClick={() => acceptEpicUpdate.mutate()}>
                Apply
              </Button>
              <Button size="sm" variant="ghost" onClick={dismissEpicUpdate}>
                Dismiss
              </Button>
            </div>
          </div>
        )}
        {proposedUpdates.map((u) => (
          <div key={u.id} className="rounded-md border border-line bg-surface p-2">
            <p className="mb-1 text-xs font-semibold text-fg">
              Edit {u.kind}: {u.current_title}
            </p>
            {u.title && <p className="text-xs text-muted">Title → {u.title}</p>}
            {u.body && <p className="mb-1 text-xs text-muted">{u.body}</p>}
            {u.acceptance_criteria?.length ? (
              <ul className="mb-2 list-disc pl-4 text-xs text-muted">
                {u.acceptance_criteria.map((ac, i) => (
                  <li key={i}>{ac}</li>
                ))}
              </ul>
            ) : null}
            <div className="flex gap-2">
              <Button
                size="sm"
                loading={applyUpdate.isPending}
                onClick={() => applyUpdate.mutate(u)}
              >
                Apply
              </Button>
              <Button size="sm" variant="ghost" onClick={() => dismissUpdate(u.id)}>
                Dismiss
              </Button>
            </div>
          </div>
        ))}
      </div>
      <form className="flex gap-1 border-t border-line p-2" onSubmit={handleSubmit}>
        <Input
          placeholder="Message the team lead…"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        {dictation.supported && (
          <IconButton
            label={dictation.listening ? "Stop dictation" : "Dictate to the team lead"}
            title="Voice input"
            aria-pressed={dictation.listening}
            onClick={dictation.toggle}
            className={dictation.listening ? "text-danger animate-pulse" : undefined}
          >
            <span aria-hidden="true">🎤</span>
          </IconButton>
        )}
        <Button type="submit" size="sm" loading={send.isPending}>Send</Button>
      </form>
    </aside>
  );
}
