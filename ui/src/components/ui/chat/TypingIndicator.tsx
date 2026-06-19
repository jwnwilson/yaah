interface TypingIndicatorProps {
  name: string;
}

export function TypingIndicator({ name }: TypingIndicatorProps) {
  return (
    <div className="flex items-center gap-1.5 rounded-xl rounded-tl-sm border border-line bg-surface px-3 py-2.5">
      <span className="sr-only">{name} is working…</span>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          data-dot
          aria-hidden="true"
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted"
          style={{ animationDelay: `${i * 0.18}s` }}
        />
      ))}
    </div>
  );
}
