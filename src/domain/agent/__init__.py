"""Agent-execution policy: the runtime protocol/DTOs, capability manifest assembly,
per-stage prompts, and Claude CLI invocation building. Pure (no I/O).

`prompts` and `capabilities` are also exposed as submodules
(``from domain.agent import prompts``) since callers use them module-style.
"""

from domain.agent import capabilities, prompts
from domain.agent.capabilities import (
    AgentManifest,
    McpRef,
    SkillRef,
    assemble,
    role_for_stage,
    select_agent,
)
from domain.agent.invocation import AgentInvocation, build_invocation
from domain.agent.runtime import AgentEvent, AgentRuntime, RunContext, StageResult

__all__ = [
    "AgentEvent",
    "AgentInvocation",
    "AgentManifest",
    "AgentRuntime",
    "McpRef",
    "RunContext",
    "SkillRef",
    "StageResult",
    "assemble",
    "build_invocation",
    "capabilities",
    "prompts",
    "role_for_stage",
    "select_agent",
]
