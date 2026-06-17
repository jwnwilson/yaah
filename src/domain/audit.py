"""Audit entity: capability/tool decisions recorded against a run."""
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from domain.base import new_id, utc_now
from domain.runs import RunStage


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
