import { useState } from "react";
import { cn } from "@/components/ui/cn";

/** Click-to-edit title. Enter or blur saves (if changed); Escape cancels. */
export function EditableTitle({
  value,
  onSave,
  className,
}: {
  value: string;
  onSave: (title: string) => void;
  className?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  if (!editing) {
    return (
      <button
        type="button"
        className={cn("truncate text-left hover:text-accent", className)}
        onClick={(e) => {
          e.stopPropagation();
          setDraft(value);
          setEditing(true);
        }}
      >
        {value}
      </button>
    );
  }

  const commit = () => {
    const t = draft.trim();
    if (t && t !== value) onSave(t);
    setEditing(false);
  };

  return (
    <input
      autoFocus
      value={draft}
      onClick={(e) => e.stopPropagation()}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") commit();
        if (e.key === "Escape") setEditing(false);
      }}
      className={cn(
        "rounded border border-line bg-canvas px-1 py-0.5 text-fg focus:outline-none focus:ring-1 focus:ring-accent",
        className,
      )}
    />
  );
}
