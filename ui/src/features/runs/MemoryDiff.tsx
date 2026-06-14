import { useState } from "react";

export function MemoryDiff({ diff }: { diff: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button className="text-blue-700 underline" onClick={() => setOpen((v) => !v)}>
        {open ? "Hide diff" : "Show diff"}
      </button>
      {open && (
        <pre className="mt-1 max-h-64 overflow-auto rounded bg-white p-2 text-[11px]">{diff}</pre>
      )}
    </div>
  );
}
