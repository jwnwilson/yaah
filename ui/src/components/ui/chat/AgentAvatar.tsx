import type { ThreadParticipant } from "./types";

const TONE: Record<string, string> = {
  lead: "bg-accent/20 text-accent",
  user: "bg-surface text-fg",
  system: "bg-surface text-muted",
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 1).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

interface AgentAvatarProps {
  participant: ThreadParticipant;
}

export function AgentAvatar({ participant }: AgentAvatarProps) {
  const tone = TONE[participant.role ?? participant.kind] ?? "bg-surface text-fg";
  return (
    <span
      title={participant.name}
      className={`grid h-7 w-7 shrink-0 place-items-center rounded-md text-xs font-bold ${tone}`}
    >
      {initials(participant.name)}
    </span>
  );
}
