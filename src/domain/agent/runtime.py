from typing import Iterator, Literal, Protocol

from pydantic import BaseModel

from domain.agent.capabilities import AgentManifest
from domain.models import RunStage
from domain.usage import TokenUsage


class AgentEvent(BaseModel):
    type: Literal["progress", "heartbeat", "artifact", "result", "notification"]
    stage: RunStage
    message: str = ""
    data: dict = {}


class StageResult(BaseModel):
    outcome: Literal["ok", "fail", "blocked"]
    artifacts: dict = {}
    cost_usd: float = 0.0
    usage: TokenUsage = TokenUsage()
    model_usage: dict[str, TokenUsage] = {}


class RunContext(BaseModel):
    run_id: str
    stage: RunStage
    task_title: str
    acceptance_criteria: list[str] = []
    workspace_path: str
    prior_artifacts: dict = {}
    instructions: str | None = None
    agent: AgentManifest | None = None


class AgentRuntime(Protocol):
    def run_stage(self, ctx: RunContext) -> Iterator[AgentEvent]: ...
    def cancel(self, run_id: str) -> None: ...


def result_of(events: list[AgentEvent]) -> StageResult:
    """Extract the StageResult carried by the final 'result' event in a stage's stream."""
    for event in reversed(events):
        if event.type == "result":
            return StageResult(**event.data)
    raise ValueError("no result event in stream")
