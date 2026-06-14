import json
from typing import Iterator

from domain.models import RunStage
from domain.runtime import AgentEvent, RunContext, StageResult
from domain.usage import TokenUsage

_DEFAULT_COST = 0.25
_FAKE_MODEL = "fake-model"
_FAKE_USAGE = TokenUsage(
    input_tokens=1000,
    output_tokens=200,
    cache_read_tokens=0,
    cache_creation_tokens=0,
    cost_usd=_DEFAULT_COST,
)


def result_of(events: list[AgentEvent]) -> StageResult:
    """Extract the StageResult carried by the final 'result' event."""
    for event in reversed(events):
        if event.type == "result":
            return StageResult(**event.data)
    raise ValueError("no result event in stream")


def _default_events(stage: RunStage) -> list[AgentEvent]:
    return [
        AgentEvent(type="progress", stage=stage, message=f"{stage} starting"),
        AgentEvent(type="heartbeat", stage=stage, message="working"),
        AgentEvent(
            type="result",
            stage=stage,
            message=f"{stage} complete",
            data=StageResult(
                outcome="ok",
                cost_usd=_DEFAULT_COST,
                usage=_FAKE_USAGE,
                model_usage={_FAKE_MODEL: _FAKE_USAGE},
            ).model_dump(),
        ),
    ]


class FakeAgentRuntime:
    """Replays a scripted event sequence per stage. Default: every stage 'ok'.
    When given a StoragePort, the IMPLEMENT stage writes a real file into the
    run workspace so the commit/PR is non-empty."""

    def __init__(self, script: dict[RunStage, list[AgentEvent]] | None = None, storage=None):
        self._script = script or {}
        self._storage = storage

    def run_stage(self, ctx: RunContext) -> Iterator[AgentEvent]:
        instr = ctx.instructions or ""
        if self._storage is not None and "decision.json" in instr:
            # Acting as the orchestrator lead: dispatch once, then ask to verify.
            decision = (
                {"intent": "continue",
                 "dispatches": [{"target_role": "backend",
                                 "instructions": "implement the task"}]}
                if "wave 0" in instr
                else {"intent": "verify"}
            )
            self._storage.write_bytes(
                f"runs/{ctx.run_id}/.orchestration/decision.json",
                json.dumps(decision).encode(),
            )
        elif self._storage is not None and "verdict.json" in instr:
            # Acting as the completion monitor.
            self._storage.write_bytes(
                f"runs/{ctx.run_id}/.orchestration/verdict.json",
                json.dumps({"complete": True}).encode(),
            )
        elif ctx.stage == RunStage.IMPLEMENT and self._storage is not None:
            self._storage.write_bytes(
                f"runs/{ctx.run_id}/IMPLEMENTED.md",
                f"# {ctx.task_title}\n\nImplemented by a faked yaah run.\n".encode(),
            )
        events = self._script.get(ctx.stage) or _default_events(ctx.stage)
        for event in events:
            yield event

    def cancel(self, run_id: str) -> None:  # no-op for the fake
        return None
