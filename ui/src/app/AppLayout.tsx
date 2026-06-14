import { NavLink, Outlet } from "react-router-dom";
import { NotificationBell } from "../features/notifications/NotificationBell";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `text-sm ${isActive ? "font-semibold text-blue-700" : "text-gray-600 hover:text-gray-900"}`;

export function AppLayout() {
  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center gap-4 border-b px-4 py-2">
        <NavLink to="/" className="text-sm font-bold">yaah</NavLink>
        <nav className="flex gap-4">
          <NavLink to="/" end className={linkClass}>Projects</NavLink>
          <NavLink to="/manage" className={linkClass}>Manage</NavLink>
        </nav>
        <div className="ml-auto">
          <NotificationBell />
        </div>
      </header>
      <main className="min-h-0 flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
