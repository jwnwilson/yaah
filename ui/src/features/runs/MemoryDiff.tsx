import { useState } from "react";

export function MemoryDiff({ diff }: { diff: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        className="mt-1 rounded text-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "Hide diff" : "Show diff"}
      </button>
      {open && (
        <pre className="mt-1 max-h-64 overflow-auto rounded bg-canvas p-2 text-[11px] text-fg">{diff}</pre>
      )}
    </div>
  );
}
