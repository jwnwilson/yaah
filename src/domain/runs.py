"""Run entity: a single ticket execution, its stage pipeline enums, and structural events."""
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from domain.base import new_id, utc_now


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
    AGENT_DISPATCHED = "agent_dispatched"
    AGENT_REPORTED = "agent_reported"
    MONITOR_STARTED = "monitor_started"
    MONITOR_VERDICT = "monitor_verdict"
    QUIESCENCE_REACHED = "quiescence_reached"


class RunEvent(BaseModel):
    id: str = Field(default_factory=new_id)
    run_id: str
    owner_id: str
    stage: RunStage | None = None
    type: RunEventType
    message: str = ""
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
