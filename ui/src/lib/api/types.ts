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
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_creation_tokens: number;
  created_at: string;
}

export type RunStage = "plan" | "provision" | "implement" | "verify" | "pr" | "learn";

export type RunEventType =
  | "stage_started"
  | "stage_completed"
  | "agent_event"
  | "gate_opened"
  | "gate_resolved"
  | "blocked"
  | "error"
  | "agent_dispatched"
  | "agent_reported"
  | "monitor_started"
  | "monitor_verdict"
  | "quiescence_reached";

export interface RunEvent {
  id: string;
  run_id: string;
  stage: RunStage | null;
  type: RunEventType;
  message: string;
  created_at: string;
  // The backend may attach an agent id on dispatch/report events; probed
  // generically by the inspector for deep-linking, never assumed present.
  agent_id?: string | null;
}

export type AuditAction = "capability_granted" | "tool_allowed" | "tool_denied";

export interface AuditEvent {
  id: string;
  run_id: string;
  stage: RunStage | string | null;
  actor: string;
  action: AuditAction;
  detail: Record<string, unknown>;
  created_at: string;
}

/** One row of the per-stage/role/model usage breakdown from GET /runs/{id}/usage. */
export interface UsageRecord {
  stage: RunStage | string | null;
  model_id: string;
  agent_role: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export interface RunUsage {
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_creation_tokens: number;
  cost_usd: number;
  total_tokens: number;
  breakdown: UsageRecord[];
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
