import os
import signal
import subprocess
from typing import Iterator

from adapters.agent.model.ports import ModelProvider
from adapters.agent.runtime import stream_json
from adapters.skills.fetcher import SkillFetcher
from domain.agent_invocation import build_invocation
from domain.runtime import AgentEvent, RunContext, StageResult


class ClaudeCodeRuntime:
    """AgentRuntime backed by the Claude Code CLI as a subprocess in the workspace.
    `spawn` is injectable so tests never launch real claude.

    All pure invocation policy (argv, tools, env, config files, skills to fetch)
    lives in `domain.agent_invocation.build_invocation`; this adapter only does I/O:
    fetch skills, write the config files, merge env, spawn, and parse the stream."""

    def __init__(self, model: ModelProvider, *, spawn=subprocess.Popen, skills=None):
        self._model = model
        self._spawn = spawn
        self._skills = skills if skills is not None else SkillFetcher()
        self._procs: dict[str, object] = {}

    def run_stage(self, ctx: RunContext) -> Iterator[AgentEvent]:
        model_id = self._model.model_id()
        if ctx.agent is not None and ctx.agent.model_alias:
            model_id = ctx.agent.model_alias
        inv = build_invocation(ctx, model_id=model_id)

        events_pre: list[AgentEvent] = []
        for name, source, dest in inv.skills:
            try:
                self._skills.fetch(source, dest)
            except Exception as exc:  # noqa: BLE001 - skip a bad skill, don't fail the stage
                events_pre.append(AgentEvent(
                    type="progress",
                    stage=ctx.stage,
                    message=f"skill '{name}' skipped: {exc}",
                ))

        for relpath, content in inv.files.items():
            path = os.path.join(ctx.workspace_path, relpath)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(content)

        env = {**os.environ, **self._model.agent_env(), **inv.env_extra}
        proc = self._spawn(
            inv.argv, cwd=ctx.workspace_path, env=env,
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
