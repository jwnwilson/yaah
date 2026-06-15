import { NavLink, Outlet } from "react-router-dom";
import { NotificationBell } from "@/features/notifications/NotificationBell";
import { ThemeToggle } from "@/features/theme/ThemeToggle";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `text-sm transition-colors ${isActive ? "font-semibold text-accent" : "text-muted hover:text-fg"}`;

export function AppLayout() {
  return (
    <div className="flex h-screen flex-col bg-canvas text-fg">
      <header className="flex items-center gap-4 border-b border-line bg-surface/80 px-4 py-2 backdrop-blur">
        <NavLink to="/" className="rounded-sm text-sm font-bold tracking-tight focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent">yaah</NavLink>
        <nav className="flex gap-4">
          <NavLink to="/" end className={linkClass}>Projects</NavLink>
          <NavLink to="/team" className={linkClass}>Team</NavLink>
          <NavLink to="/inbox" className={linkClass}>Inbox</NavLink>
          <NavLink to="/manage" className={linkClass}>Manage</NavLink>
        </nav>
        <div className="ml-auto flex items-center gap-1">
          <ThemeToggle />
          <NotificationBell />
        </div>
      </header>
      <main className="min-h-0 flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
