import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { cn } from "@/components/ui/cn";
import { NotificationBell } from "@/modules/notifications/NotificationBell";
import { CreateProjectDialog } from "@/modules/projects/CreateProjectDialog";
import { useCurrentProjectId } from "@/modules/projects/useCurrentProject";
import { useProjects } from "@/modules/projects/useProjects";
import { ThemeToggle } from "@/modules/theme/ThemeToggle";

const navClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "block rounded-md px-2 py-1.5 text-sm transition-colors",
    isActive ? "bg-accent-subtle font-medium text-accent" : "text-muted hover:bg-surface-hover hover:text-fg",
  );

function ProjectSwitcher() {
  const navigate = useNavigate();
  const currentId = useCurrentProjectId();
  const { data: projects } = useProjects();
  const [open, setOpen] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);

  const current = projects?.find((p) => p.id === currentId);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 rounded-md border border-line bg-surface px-2 py-1.5 text-left text-sm font-medium text-fg hover:bg-surface-hover"
      >
        <span className="truncate">{current?.name ?? "Select a project"}</span>
        <span className="text-subtle">▾</span>
      </button>

      {open && (
        <>
          <button
            type="button"
            aria-label="close menu"
            className="fixed inset-0 z-10 cursor-default"
            onClick={() => setOpen(false)}
          />
          <div className="absolute left-0 right-0 z-20 mt-1 max-h-72 overflow-auto rounded-md border border-line bg-surface py-1 shadow-lg">
            {projects?.length ? (
              projects.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => {
                    setOpen(false);
                    navigate(`/projects/${p.id}`);
                  }}
                  className={cn(
                    "block w-full truncate px-3 py-1.5 text-left text-sm hover:bg-surface-hover",
                    p.id === currentId ? "text-accent" : "text-fg",
                  )}
                >
                  {p.name}
                </button>
              ))
            ) : (
              <p className="px-3 py-1.5 text-xs text-subtle">No projects yet</p>
            )}
            <div className="my-1 border-t border-line" />
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                setDialogOpen(true);
              }}
              className="block w-full px-3 py-1.5 text-left text-sm text-accent hover:bg-surface-hover"
            >
              ＋ New project
            </button>
          </div>
        </>
      )}

      {currentId && (
        <nav className="mt-1 space-y-0.5 pl-1">
          <NavLink to={`/projects/${currentId}`} end className={navClass}>
            Board
          </NavLink>
          <NavLink to={`/projects/${currentId}/backlog`} className={navClass}>
            Backlog
          </NavLink>
        </nav>
      )}

      {dialogOpen && <CreateProjectDialog onClose={() => setDialogOpen(false)} />}
    </div>
  );
}

export function Sidebar() {
  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-line bg-panel">
      <div className="flex items-center justify-between px-3 py-3">
        <NavLink to="/" className="text-sm font-bold tracking-tight text-fg">
          yaah
        </NavLink>
        <div className="flex items-center gap-1">
          <ThemeToggle />
          <NotificationBell />
        </div>
      </div>

      <div className="px-3">
        <ProjectSwitcher />
      </div>

      <div className="my-3 border-t border-line" />

      <nav className="space-y-0.5 px-3">
        <NavLink to="/" end className={navClass}>
          Projects
        </NavLink>
        <NavLink to="/runs" className={navClass}>
          Runs
        </NavLink>
        <NavLink to="/inbox" className={navClass}>
          Inbox
        </NavLink>
        <NavLink to="/team" className={navClass}>
          Team
        </NavLink>
        <NavLink to="/manage" className={navClass}>
          Manage
        </NavLink>
      </nav>
    </aside>
  );
}
