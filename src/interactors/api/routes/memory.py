from fastapi import APIRouter, Depends, HTTPException, Query

from adapters.database.ports import UnitOfWork
from domain.models import MemoryProposalStatus
from interactors.api.deps import get_uow
from interactors.api.envelope import ok

router = APIRouter(tags=["memory"])

_STATUSES = {s.value for s in MemoryProposalStatus}


@router.get("/memory-proposals")
def list_memory_proposals(
    project_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page_size: int = Query(50, ge=1, le=200),
    page_number: int = Query(1, ge=1),
    uow: UnitOfWork = Depends(get_uow),
) -> dict:
    if status is not None and status not in _STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {_STATUSES}")
    filters: dict = {}
    if project_id:
        filters["project_id"] = project_id
    if status:
        filters["status"] = status
    with uow.transaction():
        page = uow.memory_proposals.list(
            filters=filters, order_by="-created_at",
            page_size=page_size, page_number=page_number,
        )
    return ok(
        [p.model_dump(mode="json") for p in page.results],
        meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number},
    )
