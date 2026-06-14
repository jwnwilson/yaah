import { Link } from "react-router-dom";
import { initials, roleVisual } from "./roleVisual";
import { useTeamRoster } from "./useTeamRoster";

export function TeamPage() {
  const { teams, agents } = useTeamRoster();

  if (teams.data && teams.data.length === 0) {
    return (
      <div className="p-6 text-muted">
        No team yet — create a default team to see your agents.
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-fg">Team</h1>
        <Link to="/manage/agents" className="text-sm text-accent hover:underline">
          Edit agents in Manage →
        </Link>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {agents.data?.map((a) => {
          const v = roleVisual(a.role);
          return (
            <div key={a.id} className="rounded-lg border border-line bg-surface p-4">
              <div className="flex items-center gap-3">
                <span
                  className="flex h-10 w-10 items-center justify-center rounded-full text-sm font-semibold text-white"
                  style={{ backgroundColor: v.color }}
                  aria-hidden
                >
                  {initials(a.name)}
                </span>
                <div className="min-w-0">
                  <div className="truncate font-medium text-fg">{a.name}</div>
                  <div className="text-xs text-muted">
                    {v.label} · {a.model_alias}
                  </div>
                </div>
              </div>
              {a.purpose && <p className="mt-3 text-sm text-muted">{a.purpose}</p>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
