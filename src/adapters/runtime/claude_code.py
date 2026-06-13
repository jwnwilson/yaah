import os
import signal
import subprocess
from typing import Iterator

from adapters.model.ports import ModelProvider
from adapters.runtime import stream_json
from domain import prompts
from domain.runtime import AgentEvent, RunContext, StageResult


class ClaudeCodeRuntime:
    """AgentRuntime backed by the Claude Code CLI as a subprocess in the workspace.
    `spawn` is injectable so tests never launch real claude."""

    def __init__(self, model: ModelProvider, *, spawn=subprocess.Popen):
        self._model = model
        self._spawn = spawn
        self._procs: dict[str, object] = {}

    def run_stage(self, ctx: RunContext) -> Iterator[AgentEvent]:
        body = ctx.prior_artifacts.get("body", "") if ctx.prior_artifacts else ""
        prompt, tools = prompts.for_stage(ctx.stage, ctx.task_title, ctx.acceptance_criteria, body)
        env = {**os.environ, **self._model.agent_env()}
        argv = [
            "claude", "-p", prompt,
            "--output-format", "stream-json", "--verbose",
            "--allowedTools", *tools,
            "--max-turns", str(prompts.max_turns(ctx.stage)),
            "--model", self._model.model_id(),
        ]
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
        yield from events

    def cancel(self, run_id: str) -> None:  # pragma: no cover - needs a real process group
        proc = self._procs.get(run_id)
        if proc is not None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
