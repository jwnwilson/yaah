from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def new_id() -> str:
    return uuid4().hex


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AutonomyLevel(StrEnum):
    GATED_ALL = "gated_all"
    GATED_MERGE = "gated_merge"
    FULL_AUTO = "full_auto"


class WorkItemKind(StrEnum):
    EPIC = "epic"
    FEATURE = "feature"
    TASK = "task"


class WorkItemStatus(StrEnum):
    DRAFT = "draft"
    REFINING = "refining"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    DONE = "done"
    BLOCKED = "blocked"
    FAILED = "failed"


class AgentRole(StrEnum):
    LEAD = "lead"
    ARCHITECT = "architect"
    BACKEND = "backend"
    FRONTEND = "frontend"
    QA = "qa"
    DEVOPS = "devops"


class Project(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    name: str
    repo_url: str | None = None
    local_path: str | None = None
    team_id: str | None = None
    autonomy: AutonomyLevel = AutonomyLevel.GATED_ALL
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _needs_a_repo(self) -> "Project":
        if not self.repo_url and not self.local_path:
            raise ValueError("project needs repo_url or local_path")
        return self


class WorkItem(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    project_id: str
    kind: WorkItemKind
    parent_id: str | None = None
    title: str
    body: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    status: WorkItemStatus = WorkItemStatus.DRAFT
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _hierarchy_rules(self) -> "WorkItem":
        if self.kind == WorkItemKind.EPIC and self.parent_id:
            raise ValueError("epics cannot have a parent")
        if self.kind in (WorkItemKind.FEATURE, WorkItemKind.TASK) and not self.parent_id:
            raise ValueError(f"{self.kind} requires parent_id")
        return self


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    DONE = "done"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class RunStage(StrEnum):
    PLAN = "plan"
    PROVISION = "provision"
    IMPLEMENT = "implement"
    VERIFY = "verify"
    PR = "pr"
    LEARN = "learn"


class RunEventType(StrEnum):
    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"
    AGENT_EVENT = "agent_event"
    GATE_OPENED = "gate_opened"
    GATE_RESOLVED = "gate_resolved"
    BLOCKED = "blocked"
    ERROR = "error"


class RunEvent(BaseModel):
    id: str = Field(default_factory=new_id)
    run_id: str
    owner_id: str
    stage: RunStage | None = None
    type: RunEventType
    message: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class Team(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    name: str
    created_at: datetime = Field(default_factory=utc_now)


class Skill(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    name: str
    description: str = ""
    source: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class McpServer(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    name: str
    transport: Literal["stdio", "http"] = "stdio"
    command_or_url: str = ""
    tool_allowlist: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class Secret(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    name: str
    description: str = ""
    encrypted_value: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class AgentDefinition(BaseModel):
    id: str = Field(default_factory=new_id)
    team_id: str
    role: AgentRole
    name: str
    persona: str = ""
    model_alias: str
    runtime: str = "claude_code"
    purpose: str = ""
    system_prompt: str = ""
    allowed_tools: list[str] = Field(default_factory=list)
    skill_ids: list[str] = Field(default_factory=list)
    mcp_server_ids: list[str] = Field(default_factory=list)
    secret_ids: list[str] = Field(default_factory=list)


class AuditAction(StrEnum):
    CAPABILITY_GRANTED = "capability_granted"
    TOOL_ALLOWED = "tool_allowed"
    TOOL_DENIED = "tool_denied"


class AuditEvent(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    run_id: str
    stage: RunStage | None = None
    actor: str = ""
    action: AuditAction
    detail: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class Run(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    task_id: str
    team_id: str
    status: RunStatus = RunStatus.PENDING
    stage: str | None = None
    branch: str | None = None
    pr_url: str | None = None
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    created_at: datetime = Field(default_factory=utc_now)


class UsageRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    run_id: str
    work_item_id: str
    project_id: str
    stage: RunStage
    agent_role: AgentRole | None = None
    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float = 0.0
    created_at: datetime = Field(default_factory=utc_now)

    @property
    def dedupe_key(self) -> str:
        role = self.agent_role.value if self.agent_role else "none"
        return f"{self.run_id}:{self.stage.value}:{role}:{self.model_id}"
