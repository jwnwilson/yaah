from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from adapters.database.ports import UnitOfWork
from domain.usage import TokenUsage, UsageRecord, group_by, rollup
from interactors.api.deps import get_uow
from interactors.api.envelope import ok

router = APIRouter(tags=["usage"])

_GROUP_KEYS = {"stage", "agent_role", "model"}


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


def _validate_group(group: str | None) -> None:
    if group is not None and group not in _GROUP_KEYS:
        raise HTTPException(status_code=422, detail=f"group_by must be one of {_GROUP_KEYS}")


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


def _descendant_ids(uow: UnitOfWork, root_id: str) -> list[str]:
    """root + children + grandchildren (epic->feature->task is the deepest hierarchy)."""
    ids = [root_id]
    children = uow.work_items.list(filters={"parent_id": root_id}, page_size=1000).results
    ids += [c.id for c in children]
    for child in children:
        grand = uow.work_items.list(filters={"parent_id": child.id}, page_size=1000).results
        ids += [g.id for g in grand]
    return ids


@router.get("/work-items/{item_id}/usage")
def work_item_usage(
    item_id: str,
    group_by: str | None = Query(default=None),
    uow: UnitOfWork = Depends(get_uow),
) -> dict:
    _validate_group(group_by)
    with uow.transaction():
        uow.work_items.get(item_id)  # 404 / owner scope
        ids = _descendant_ids(uow, item_id)
        records = uow.usage.list(filters={"work_item_id__in": ids}, page_size=10000).results
    return ok(_payload(records, group_by))


@router.get("/projects/{project_id}/usage")
def project_usage(
    project_id: str,
    group_by: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    uow: UnitOfWork = Depends(get_uow),
) -> dict:
    _validate_group(group_by)
    if since and until and since > until:
        raise HTTPException(status_code=422, detail="since must be <= until")
    filters: dict = {"project_id": project_id}
    if since:
        filters["created_at__gte"] = since
    if until:
        filters["created_at__lte"] = until
    with uow.transaction():
        uow.projects.get(project_id)  # 404 / owner scope
        records = uow.usage.list(filters=filters, page_size=10000).results
    return ok(_payload(records, group_by))


@router.get("/usage")
def global_usage(
    project_id: str | None = Query(default=None),
    group_by: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    uow: UnitOfWork = Depends(get_uow),
) -> dict:
    _validate_group(group_by)
    if since and until and since > until:
        raise HTTPException(status_code=422, detail="since must be <= until")
    filters: dict = {}
    if project_id:
        filters["project_id"] = project_id
    if since:
        filters["created_at__gte"] = since
    if until:
        filters["created_at__lte"] = until
    with uow.transaction():
        records = uow.usage.list(filters=filters, page_size=10000).results
    return ok(_payload(records, group_by))
