from typing import Iterator, Literal, Protocol

from pydantic import BaseModel

from domain.capabilities import AgentManifest
from domain.models import RunStage


class AgentEvent(BaseModel):
    type: Literal["progress", "heartbeat", "artifact", "result", "notification"]
    stage: RunStage
    message: str = ""
    data: dict = {}


class StageResult(BaseModel):
    outcome: Literal["ok", "fail", "blocked"]
    artifacts: dict = {}
    cost_usd: float = 0.0


class RunContext(BaseModel):
    run_id: str
    stage: RunStage
    task_title: str
    acceptance_criteria: list[str] = []
    workspace_path: str
    prior_artifacts: dict = {}
    agent: AgentManifest | None = None


class AgentRuntime(Protocol):
    def run_stage(self, ctx: RunContext) -> Iterator[AgentEvent]: ...
    def cancel(self, run_id: str) -> None: ...
