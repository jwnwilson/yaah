from fastapi import APIRouter, Depends

from adapters.database.ports import UnitOfWork
from domain.models import UsageRecord
from domain.usage import TokenUsage, group_by, rollup
from interactors.api.deps import get_uow
from interactors.api.envelope import ok

router = APIRouter(tags=["usage"])


def _usage_of(rec: UsageRecord) -> TokenUsage:
    return TokenUsage(
        input_tokens=rec.input_tokens, output_tokens=rec.output_tokens,
        cache_read_tokens=rec.cache_read_tokens,
        cache_creation_tokens=rec.cache_creation_tokens, cost_usd=rec.cost_usd,
    )


def _key_of(rec: UsageRecord, group: str) -> str:
    if group == "stage":
        return rec.stage.value
    if group == "agent_role":
        return rec.agent_role.value if rec.agent_role else "unknown"
    return rec.model_id


def _dump(u: TokenUsage) -> dict:
    return {**u.model_dump(), "total_tokens": u.total_tokens}


def _payload(records: list[UsageRecord], group: str | None) -> dict:
    data: dict = {"totals": _dump(rollup(_usage_of(r) for r in records))}
    if group:
        grouped = group_by((_key_of(r, group), _usage_of(r)) for r in records)
        data["group_by"] = group
        data["groups"] = {k: _dump(v) for k, v in grouped.items()}
    return data


@router.get("/runs/{run_id}/usage")
def run_usage(run_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        uow.runs.get(run_id)  # 404 / owner scope
        records = uow.usage.list(filters={"run_id": run_id}, page_size=1000).results
    breakdown = [
        {"stage": r.stage.value, "model_id": r.model_id,
         "agent_role": r.agent_role.value if r.agent_role else None, **_dump(_usage_of(r))}
        for r in records
    ]
    return ok({**_payload(records, None), "breakdown": breakdown})
