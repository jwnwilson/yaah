import { NavLink, Outlet } from "react-router-dom";

const items = [
  { to: "/manage/secrets", label: "Secrets" },
  { to: "/manage/skills", label: "Skills" },
  { to: "/manage/mcp-servers", label: "MCP servers" },
];

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `block rounded-md px-3 py-2 text-sm transition-colors ${
    isActive ? "bg-accent-subtle font-medium text-accent" : "text-muted hover:bg-surface-hover hover:text-fg"
  }`;

export function ManageLayout() {
  return (
    <div className="flex h-full bg-canvas">
      <aside className="w-48 shrink-0 border-r border-line bg-panel p-3">
        <nav className="space-y-1">
          {items.map((i) => (
            <NavLink key={i.to} to={i.to} className={linkClass}>{i.label}</NavLink>
          ))}
        </nav>
      </aside>
      <section className="flex-1 overflow-auto p-6">
        <Outlet />
      </section>
    </div>
  );
}
