import type { ReactNode } from "react";
import { MessageBubble } from "./MessageBubble";
import type { ThreadMessage } from "./types";
import { TypingIndicator } from "./TypingIndicator";

interface ChatThreadProps {
  messages: ThreadMessage[];
  readOnly?: boolean;
  processing?: { name: string } | null;
  composer?: ReactNode;
  proposalSlot?: ReactNode;
}

function participantKey(p: ThreadMessage["sender"]): string {
  return p.id ?? `${p.kind}:${p.name}`;
}

export function ChatThread({ messages, readOnly, processing, composer, proposalSlot }: ChatThreadProps) {
  const participants = new Set<string>();
  let hasRecipient = false;
  for (const m of messages) {
    participants.add(participantKey(m.sender));
    if (m.recipient) hasRecipient = true;
  }
  const multi = hasRecipient || participants.size > 2;

  return (
    <div className="flex h-full flex-col">
      {readOnly && (
        <div className="flex justify-end border-b border-line px-3 py-1.5">
          <span className="rounded-full border border-line bg-surface px-2.5 py-0.5 text-xs text-muted">
            👁 read-only
          </span>
        </div>
      )}
      <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-3">
        {messages.length === 0 ? (
          <p className="m-auto text-sm text-muted">No messages yet</p>
        ) : (
          messages.map((m) => <MessageBubble key={m.id} message={m} multi={multi} />)
        )}
        {processing && (
          <div className="max-w-[90%]">
            <TypingIndicator name={processing.name} />
          </div>
        )}
        {proposalSlot}
      </div>
      {!readOnly && composer}
    </div>
  );
}
