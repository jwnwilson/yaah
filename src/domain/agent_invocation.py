"""Pure policy that builds the Claude Code CLI invocation for a run stage. No I/O."""

import json
import os

from pydantic import BaseModel

from domain import prompts
from domain.runtime import RunContext

_HOOK_COMMAND = "python -m adapters.agent.runtime.pretooluse_hook"
_SETTINGS = {
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "*",
                "hooks": [{"type": "command", "command": _HOOK_COMMAND}],
            }
        ]
    }
}


class AgentInvocation(BaseModel):
    argv: list[str]
    env_extra: dict[str, str] = {}
    files: dict[str, str] = {}                # relpath -> JSON content
    skills: list[tuple[str, str, str]] = []   # (name, source, dest)
    mcp_config_path: str | None = None


def _mcp_config(servers, secret_env) -> dict:
    env = secret_env or {}
    mcp: dict = {}
    for s in servers:
        entry = (
            {"command": s.command_or_url}
            if s.transport == "stdio"
            else {"url": s.command_or_url}
        )
        if env:
            entry["env"] = dict(env)
        mcp[s.name] = entry
    return {"mcpServers": mcp}


def build_invocation(ctx: RunContext, *, model_id: str) -> AgentInvocation:
    body = ctx.prior_artifacts.get("body", "") if ctx.prior_artifacts else ""
    task_prompt, default_tools = prompts.for_stage(
        ctx.stage, ctx.task_title, ctx.acceptance_criteria, body
    )
    if ctx.instructions:
        task_prompt = ctx.instructions
    argv = ["claude", "-p", task_prompt, "--output-format", "stream-json", "--verbose"]
    tools = list(default_tools)
    files: dict[str, str] = {}
    env_extra: dict[str, str] = {}
    skills: list[tuple[str, str, str]] = []
    mcp_config_path: str | None = None

    agent = ctx.agent
    if agent is not None:
        if agent.system_prompt:
            argv += ["--append-system-prompt", agent.system_prompt]
        tools = list(agent.allowed_tools) if agent.allowed_tools else list(default_tools)
        for mcp in agent.mcp_servers:
            tools += mcp.tool_allowlist
        for skill in agent.skills:
            dest = os.path.join(ctx.workspace_path, ".claude", "skills", skill.name)
            skills.append((skill.name, skill.source, dest))
        if agent.mcp_servers:
            files[".mcp.json"] = json.dumps(_mcp_config(agent.mcp_servers, agent.secret_env))
            mcp_config_path = os.path.join(ctx.workspace_path, ".mcp.json")
            argv += ["--mcp-config", mcp_config_path]

    argv += [
        "--allowedTools", *tools,
        "--max-turns", str(prompts.max_turns(ctx.stage)),
        "--model", model_id,
    ]

    if agent is not None:
        files[".claude/settings.json"] = json.dumps(_SETTINGS)
        env_extra = {
            **(agent.secret_env or {}),
            "YAAH_ALLOWED_TOOLS": json.dumps(tools),
            "YAAH_AUDIT_PATH": os.path.join(ctx.workspace_path, "audit.jsonl"),
            "YAAH_RUN_ID": ctx.run_id,
            "YAAH_STAGE": str(ctx.stage.value),
        }

    return AgentInvocation(
        argv=argv,
        env_extra=env_extra,
        files=files,
        skills=skills,
        mcp_config_path=mcp_config_path,
    )
