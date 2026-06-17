from datetime import datetime
from typing import Iterable

from pydantic import BaseModel, Field

from domain.agent.models import AgentRole
from domain.base import new_id, utc_now
from domain.runs import RunStage


class UsageRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    run_id: str
    work_item_id: str
    project_id: str
    stage: RunStage
    agent_role: AgentRole | None = None
    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float = 0.0
    created_at: datetime = Field(default_factory=utc_now)

    @property
    def dedupe_key(self) -> str:
        role = self.agent_role.value if self.agent_role else "none"
        return f"{self.run_id}:{self.stage.value}:{role}:{self.model_id}"


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_creation_tokens
        )

    def combine(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_creation_tokens=self.cache_creation_tokens + other.cache_creation_tokens,
            cost_usd=self.cost_usd + other.cost_usd,
        )


ZERO_USAGE = TokenUsage()


def rollup(items: Iterable[TokenUsage]) -> TokenUsage:
    total = ZERO_USAGE
    for item in items:
        total = total.combine(item)
    return total


def group_by(pairs: Iterable[tuple[str, TokenUsage]]) -> dict[str, TokenUsage]:
    """pairs: (bucket_key, usage). Buckets are summed via combine."""
    out: dict[str, TokenUsage] = {}
    for key, usage in pairs:
        out[key] = out.get(key, ZERO_USAGE).combine(usage)
    return out
