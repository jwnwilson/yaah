import json
import os
import signal
import subprocess
from typing import Iterator

from adapters.model.ports import ModelProvider
from adapters.runtime import stream_json
from adapters.skills.fetcher import SkillFetcher
from domain import prompts
from domain.capabilities import McpRef
from domain.runtime import AgentEvent, RunContext, StageResult


def _write_mcp_config(workspace_path: str, servers: list[McpRef],
                      secret_env: dict | None = None) -> None:
    env = secret_env or {}
    mcp = {}
    for s in servers:
        entry = (
            {"command": s.command_or_url}
            if s.transport == "stdio"
            else {"url": s.command_or_url}
        )
        if env:
            entry["env"] = dict(env)
        mcp[s.name] = entry
    with open(os.path.join(workspace_path, ".mcp.json"), "w") as f:
        json.dump({"mcpServers": mcp}, f)


class ClaudeCodeRuntime:
    """AgentRuntime backed by the Claude Code CLI as a subprocess in the workspace.
    `spawn` is injectable so tests never launch real claude."""

    def __init__(self, model: ModelProvider, *, spawn=subprocess.Popen, skills=None):
        self._model = model
        self._spawn = spawn
        self._skills = skills if skills is not None else SkillFetcher()
        self._procs: dict[str, object] = {}

    def run_stage(self, ctx: RunContext) -> Iterator[AgentEvent]:
        body = ctx.prior_artifacts.get("body", "") if ctx.prior_artifacts else ""
        task_prompt, default_tools = prompts.for_stage(
            ctx.stage, ctx.task_title, ctx.acceptance_criteria, body
        )

        events_pre: list[AgentEvent] = []
        argv = ["claude", "-p", task_prompt, "--output-format", "stream-json", "--verbose"]
        tools = list(default_tools)

        if ctx.agent is not None:
            if ctx.agent.system_prompt:
                argv += ["--append-system-prompt", ctx.agent.system_prompt]
            tools = (
                list(ctx.agent.allowed_tools) if ctx.agent.allowed_tools else list(default_tools)
            )
            for mcp in ctx.agent.mcp_servers:
                tools += mcp.tool_allowlist
            for skill in ctx.agent.skills:
                dest = os.path.join(ctx.workspace_path, ".claude", "skills", skill.name)
                try:
                    self._skills.fetch(skill.source, dest)
                except Exception as exc:  # noqa: BLE001 - skip a bad skill, don't fail the stage
                    events_pre.append(AgentEvent(
                        type="progress",
                        stage=ctx.stage,
                        message=f"skill '{skill.name}' skipped: {exc}",
                    ))
            if ctx.agent.mcp_servers:
                _write_mcp_config(ctx.workspace_path, ctx.agent.mcp_servers, ctx.agent.secret_env)
                argv += ["--mcp-config", os.path.join(ctx.workspace_path, ".mcp.json")]

        argv += [
            "--allowedTools", *tools,
            "--max-turns", str(prompts.max_turns(ctx.stage)),
            "--model", self._model.model_id(),
        ]

        env = {**os.environ, **self._model.agent_env()}
        if ctx.agent is not None and ctx.agent.secret_env:
            env = {**env, **ctx.agent.secret_env}
        proc = self._spawn(
            argv, cwd=ctx.workspace_path, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
        )
        self._procs[ctx.run_id] = proc
        try:
            events, _result = stream_json.parse(proc.stdout, ctx.stage)
        finally:
            proc.wait()
            self._procs.pop(ctx.run_id, None)

        if not any(e.type == "result" for e in events):
            fail = StageResult(outcome="fail")
            events.append(AgentEvent(
                type="result", stage=ctx.stage,
                message="claude exited without a result", data=fail.model_dump(),
            ))

        yield from events_pre
        yield from events

    def cancel(self, run_id: str) -> None:  # pragma: no cover - needs a real process group
        proc = self._procs.get(run_id)
        if proc is not None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
