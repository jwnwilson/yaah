const ROLE_STYLE: Record<string, { color: string; label: string }> = {
  lead: { color: "#a855f7", label: "Lead" },
  architect: { color: "#06b6d4", label: "Architect" },
  backend: { color: "#3b82f6", label: "Backend" },
  frontend: { color: "#ec4899", label: "Frontend" },
  qa: { color: "#22c55e", label: "QA" },
  devops: { color: "#f59e0b", label: "DevOps" },
};

export interface RoleVisual {
  color: string;
  label: string;
}

/** Deterministic colour + label for an agent role, used everywhere an agent
 *  appears (roster, assignee chip, message sender). */
export function roleVisual(role: string): RoleVisual {
  return ROLE_STYLE[role] ?? { color: "#64748b", label: role };
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const text = parts.map((w) => w[0]).join("").slice(0, 2);
  return text ? text.toUpperCase() : "?";
}
