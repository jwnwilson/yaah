from typing import Literal

from pydantic import BaseModel

from domain.models import McpServer, Secret, Skill
from lib.crud_router import CrudRouter


class CreateSkill(BaseModel):
    name: str
    description: str = ""
    source: str = ""


class UpdateSkill(BaseModel):
    name: str | None = None
    description: str | None = None
    source: str | None = None


class CreateMcpServer(BaseModel):
    name: str
    transport: Literal["stdio", "http"] = "stdio"
    command_or_url: str = ""
    tool_allowlist: list[str] = []


class UpdateMcpServer(BaseModel):
    name: str | None = None
    transport: Literal["stdio", "http"] | None = None
    command_or_url: str | None = None
    tool_allowlist: list[str] | None = None


class CreateSecret(BaseModel):
    name: str
    description: str = ""


class UpdateSecret(BaseModel):
    name: str | None = None
    description: str | None = None


skills_router = CrudRouter(
    repository="skills",
    response_dto=Skill,
    create_schema=CreateSkill,
    update_schema=UpdateSkill,
    methods=("CREATE", "READ", "UPDATE", "DELETE"),
    prefix="/skills",
    tags=["capabilities"],
)

mcp_router = CrudRouter(
    repository="mcp_servers",
    response_dto=McpServer,
    create_schema=CreateMcpServer,
    update_schema=UpdateMcpServer,
    methods=("CREATE", "READ", "UPDATE", "DELETE"),
    prefix="/mcp-servers",
    tags=["capabilities"],
)

secrets_router = CrudRouter(
    repository="secrets",
    response_dto=Secret,
    create_schema=CreateSecret,
    update_schema=UpdateSecret,
    methods=("CREATE", "READ", "UPDATE", "DELETE"),
    prefix="/secrets",
    tags=["capabilities"],
)
