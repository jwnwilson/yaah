"""Pure agent-capability policy: stage->role, agent selection, manifest assembly. No I/O."""

from pydantic import BaseModel

from domain.agent.capability_grants import McpServer, Skill
from domain.agent.models import AgentDefinition, AgentRole
from domain.runs import RunStage

_STAGE_ROLE: dict[RunStage, AgentRole] = {
    RunStage.PLAN: AgentRole.LEAD,
    RunStage.IMPLEMENT: AgentRole.BACKEND,
    RunStage.VERIFY: AgentRole.QA,
    RunStage.LEARN: AgentRole.LEAD,
}


class SkillRef(BaseModel):
    name: str
    source: str


class McpRef(BaseModel):
    name: str
    transport: str
    command_or_url: str
    tool_allowlist: list[str] = []


class AgentManifest(BaseModel):
    system_prompt: str = ""
    allowed_tools: list[str] = []
    skills: list[SkillRef] = []
    mcp_servers: list[McpRef] = []
    secret_env: dict[str, str] = {}
    model_alias: str = ""


def role_for_stage(stage: RunStage) -> AgentRole | None:
    return _STAGE_ROLE.get(stage)


def select_agent(agents: list[AgentDefinition], stage: RunStage) -> AgentDefinition | None:
    if not agents:
        return None
    role = role_for_stage(stage)
    by_role = {a.role: a for a in agents}
    if role is not None and role in by_role:
        return by_role[role]
    if AgentRole.LEAD in by_role:
        return by_role[AgentRole.LEAD]
    return agents[0]


def assemble(
    agent: AgentDefinition,
    skills: list[Skill],
    mcp_servers: list[McpServer],
) -> AgentManifest:
    return AgentManifest(
        system_prompt=agent.system_prompt,
        allowed_tools=list(agent.allowed_tools),
        skills=[SkillRef(name=s.name, source=s.source) for s in skills],
        mcp_servers=[
            McpRef(
                name=m.name,
                transport=m.transport,
                command_or_url=m.command_or_url,
                tool_allowlist=list(m.tool_allowlist),
            )
            for m in mcp_servers
        ],
        model_alias=agent.model_alias,
    )
