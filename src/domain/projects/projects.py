"""Project entity: a repository under management with an autonomy policy."""
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from domain.base import new_id, utc_now


class AutonomyLevel(StrEnum):
    GATED_ALL = "gated_all"
    GATED_MERGE = "gated_merge"
    FULL_AUTO = "full_auto"


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
