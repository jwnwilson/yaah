import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ChatComposer } from "@/components/ui/chat/ChatComposer";
import { ChatThread } from "@/components/ui/chat/ChatThread";
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
    messages,
    send,
    processing,
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

  const proposalSlot = (
    <>
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
            <Button size="sm" loading={applyUpdate.isPending} onClick={() => applyUpdate.mutate(u)}>
              Apply
            </Button>
            <Button size="sm" variant="ghost" onClick={() => dismissUpdate(u.id)}>
              Dismiss
            </Button>
          </div>
        </div>
      ))}
    </>
  );

  return (
    <aside className="flex h-full w-80 shrink-0 flex-col border-l border-line bg-panel">
      <h2 className="border-b border-line p-2 text-sm font-semibold text-fg">
        {epicId ? "Team lead — focused on epic" : "Team lead"}
      </h2>
      <ChatThread
        messages={messages}
        processing={processing}
        proposalSlot={proposalSlot}
        composer={
          <ChatComposer
            value={text}
            onChange={setText}
            onSubmit={(t) => {
              send.mutate(t);
              setText("");
            }}
            placeholder="Message the team lead…"
            sending={send.isPending}
            micSupported={dictation.supported}
            micListening={dictation.listening}
            onMicToggle={dictation.toggle}
          />
        }
      />
    </aside>
  );
}
