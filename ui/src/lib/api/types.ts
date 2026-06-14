export type WorkItemKind = "epic" | "feature" | "task";

export type WorkItemStatus =
  | "draft"
  | "refining"
  | "ready"
  | "in_progress"
  | "in_review"
  | "approved"
  | "done"
  | "blocked"
  | "failed";

export type AutonomyLevel = "gated_all" | "gated_merge" | "full_auto";

export type RunStatus =
  | "pending"
  | "running"
  | "awaiting_approval"
  | "done"
  | "failed"
  | "blocked"
  | "cancelled";

export interface Project {
  id: string;
  owner_id: string;
  name: string;
  repo_url: string | null;
  local_path: string | null;
  team_id: string | null;
  autonomy: AutonomyLevel;
  created_at: string;
}

export interface WorkItem {
  id: string;
  project_id: string;
  owner_id: string;
  kind: WorkItemKind;
  parent_id: string | null;
  title: string;
  body: string;
  acceptance_criteria: string[];
  status: WorkItemStatus;
  assignee_agent_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface Run {
  id: string;
  owner_id: string;
  task_id: string;
  team_id: string;
  status: RunStatus;
  stage: string | null;
  branch: string | null;
  pr_url: string | null;
  cost_usd: number;
  created_at: string;
}

export interface Secret {
  id: string;
  owner_id: string;
  name: string;
  description: string;
  has_value: boolean;
  created_at: string;
}

export interface Skill {
  id: string;
  owner_id: string;
  name: string;
  description: string;
  source: string;
  created_at: string;
}

export type McpTransport = "stdio" | "http";

export interface McpServer {
  id: string;
  owner_id: string;
  name: string;
  transport: McpTransport;
  command_or_url: string;
  tool_allowlist: string[];
  created_at: string;
}
