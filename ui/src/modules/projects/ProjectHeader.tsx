import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { Button } from "@/components/ui/Button";

const navClass = ({ isActive }: { isActive: boolean }) =>
  `text-sm transition-colors ${isActive ? "font-semibold text-accent" : "text-muted hover:text-fg"}`;

/** Shared top bar for a project's Board and Backlog views: Projects link, Board/Backlog
 * tabs, optional page-specific controls, and the Team lead chat toggle. */
export function ProjectHeader({
  projectId,
  showChat,
  onToggleChat,
  extra,
}: {
  projectId: string;
  showChat: boolean;
  onToggleChat: () => void;
  extra?: ReactNode;
}) {
  return (
    <header className="flex items-center gap-3 border-b border-line bg-surface px-4 py-3">
      <Link to="/" className="text-sm text-accent hover:underline">
        ← Projects
      </Link>
      <NavLink to={`/projects/${projectId}`} end className={navClass}>
        Board
      </NavLink>
      <NavLink to={`/projects/${projectId}/backlog`} className={navClass}>
        Backlog
      </NavLink>
      <div className="ml-auto flex items-center gap-3">
        {extra}
        <Button size="sm" variant="secondary" onClick={onToggleChat}>
          {showChat ? "Hide chat" : "Team lead"}
        </Button>
      </div>
    </header>
  );
}
