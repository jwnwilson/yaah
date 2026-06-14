import { NavLink, Outlet } from "react-router-dom";

const items = [
  { to: "/manage/secrets", label: "Secrets" },
  { to: "/manage/skills", label: "Skills" },
  { to: "/manage/mcp-servers", label: "MCP servers" },
];

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `block rounded px-3 py-2 text-sm ${isActive ? "bg-blue-50 font-medium text-blue-700" : "text-gray-700 hover:bg-gray-50"}`;

export function ManageLayout() {
  return (
    <div className="flex h-full">
      <aside className="w-48 shrink-0 border-r p-3">
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
