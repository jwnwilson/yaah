import { useState } from "react";
import { Button } from "@/components/ui/Button";
import type { BacklogView } from "@/lib/api/backlog";

function Toggle({ active, onClick }: { active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        active
          ? "rounded-full bg-accent-subtle px-2 py-0.5 text-xs font-medium text-accent"
          : "rounded-full bg-surface-hover px-2 py-0.5 text-xs font-medium text-muted hover:text-fg"
      }
    >
      {active ? "active" : "activate"}
    </button>
  );
}

/** Board control to move epics/features on/off the board (active = on the board). */
export function ActivePopover({
  data,
  onActivate,
  onDeactivate,
}: {
  data?: BacklogView;
  onActivate: (id: string) => void;
  onDeactivate: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const toggle = (id: string, active: boolean) => (active ? onDeactivate(id) : onActivate(id));

  return (
    <div className="relative">
      <Button size="sm" variant="secondary" onClick={() => setOpen((v) => !v)}>
        Active ▾
      </Button>
      {open && (
        <>
          <button
            type="button"
            aria-label="close menu"
            className="fixed inset-0 z-10 cursor-default"
            onClick={() => setOpen(false)}
          />
          <div className="absolute right-0 z-20 mt-1 max-h-96 w-72 overflow-auto rounded-md border border-line bg-surface p-2 shadow-lg">
            {data?.epics.length ? (
              data.epics.map((be) => (
                <div key={be.epic.id} className="mb-2">
                  <div className="flex items-center gap-2 px-1 py-1">
                    <span className="flex-1 truncate text-sm font-medium text-fg">
                      {be.epic.title}
                    </span>
                    <Toggle active={be.active} onClick={() => toggle(be.epic.id, be.active)} />
                  </div>
                  {be.features.map((bf) => (
                    <div key={bf.feature.id} className="flex items-center gap-2 px-1 py-0.5 pl-4">
                      <span className="flex-1 truncate text-xs text-muted">{bf.feature.title}</span>
                      <Toggle
                        active={bf.feature.active}
                        onClick={() => toggle(bf.feature.id, bf.feature.active)}
                      />
                    </div>
                  ))}
                </div>
              ))
            ) : (
              <p className="px-1 py-1 text-xs text-subtle">No epics yet — add them in the backlog.</p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
