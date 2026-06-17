"""Capability-grant entities: owner-scoped skills, MCP servers, and secrets that can
be granted to agents. Distinct from the sibling `domain.agent.capabilities`, which
assembles the per-run capability manifest (execution policy) from these grants."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from domain.base import new_id, utc_now


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
