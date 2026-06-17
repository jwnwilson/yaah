"""Agent/team entities: roles, the team container, and the agent definition."""
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from domain.base import new_id, utc_now


class AgentRole(StrEnum):
    LEAD = "lead"
    ARCHITECT = "architect"
    BACKEND = "backend"
    FRONTEND = "frontend"
    QA = "qa"
    DEVOPS = "devops"


class Team(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    name: str
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
