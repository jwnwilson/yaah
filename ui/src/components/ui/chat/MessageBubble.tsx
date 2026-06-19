import { AgentAvatar } from "./AgentAvatar";
import type { ThreadMessage } from "./types";

const KIND_TONE: Record<string, string> = {
  dispatch: "bg-accent/15 text-accent",
  report: "bg-surface text-fg",
  status: "bg-surface text-muted",
  notice: "bg-surface text-muted",
  gate: "bg-danger/15 text-danger",
  chat: "bg-surface text-fg",
};

interface MessageBubbleProps {
  message: ThreadMessage;
  multi: boolean;
}

export function MessageBubble({ message, multi }: MessageBubbleProps) {
  const isMe = !multi && message.sender.kind === "user";
  const who = message.recipient
    ? `${message.sender.name} → ${message.recipient.name}`
    : message.sender.name;

  return (
    <div className={`flex max-w-[90%] gap-2.5 ${isMe ? "flex-row-reverse self-end" : ""}`}>
      <AgentAvatar participant={message.sender} />
      <div>
        {!isMe && (
          <div className="mb-0.5 flex items-center gap-2 text-xs text-muted">
            <span>{who}</span>
            {multi && (
              <span className={`rounded px-1.5 py-px text-[10px] font-bold uppercase tracking-wide ${KIND_TONE[message.kind]}`}>
                {message.kind}
              </span>
            )}
          </div>
        )}
        <div
          className={`whitespace-pre-wrap rounded-xl px-3 py-2 text-sm ${
            isMe
              ? "rounded-tr-sm bg-accent text-accent-fg"
              : "rounded-tl-sm border border-line bg-surface text-fg"
          }`}
        >
          {message.body}
        </div>
      </div>
    </div>
  );
}
