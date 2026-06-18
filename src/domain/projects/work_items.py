"""Work-item entity: the epic/feature/task hierarchy and its status enum."""
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from domain.base import new_id, utc_now


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
    assignee_agent_id: str | None = None
    active: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _hierarchy_rules(self) -> "WorkItem":
        if self.kind == WorkItemKind.EPIC and self.parent_id:
            raise ValueError("epics cannot have a parent")
        if self.kind in (WorkItemKind.FEATURE, WorkItemKind.TASK) and not self.parent_id:
            raise ValueError(f"{self.kind} requires parent_id")
        if self.active and self.kind != WorkItemKind.EPIC:
            raise ValueError("only epics can be active")
        return self
