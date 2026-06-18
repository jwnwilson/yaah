import { useState } from "react";
import { cn } from "@/components/ui/cn";

/** A "+ label" affordance that opens an inline input. Enter creates and stays open
 * for the next item; Escape or blur (when empty) closes. */
export function InlineAdd({
  label,
  onAdd,
  className,
}: {
  label: string;
  onAdd: (title: string) => void;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");

  if (!open) {
    return (
      <button
        type="button"
        className={cn("text-left text-xs text-subtle hover:text-fg", className)}
        onClick={() => setOpen(true)}
      >
        + {label}
      </button>
    );
  }

  const commit = () => {
    const t = draft.trim();
    if (t) {
      onAdd(t);
      setDraft("");
    }
  };

  return (
    <input
      autoFocus
      value={draft}
      placeholder={label}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => {
        if (!draft.trim()) setOpen(false);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") commit();
        if (e.key === "Escape") {
          setDraft("");
          setOpen(false);
        }
      }}
      className={cn(
        "rounded border border-line bg-canvas px-2 py-1 text-sm text-fg focus:outline-none focus:ring-1 focus:ring-accent",
        className,
      )}
    />
  );
}
