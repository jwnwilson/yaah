from typing import Iterator

from domain.models import RunStage
from domain.runtime import AgentEvent, RunContext, StageResult

_DEFAULT_COST = 0.25


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
            data=StageResult(outcome="ok", cost_usd=_DEFAULT_COST).model_dump(),
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
        if ctx.stage == RunStage.IMPLEMENT and self._storage is not None:
            self._storage.write_bytes(
                f"runs/{ctx.run_id}/IMPLEMENTED.md",
                f"# {ctx.task_title}\n\nImplemented by a faked yaah run.\n".encode(),
            )
        events = self._script.get(ctx.stage) or _default_events(ctx.stage)
        for event in events:
            yield event

    def cancel(self, run_id: str) -> None:  # no-op for the fake
        return None
