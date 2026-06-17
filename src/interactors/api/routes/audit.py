from fastapi import APIRouter, Depends, HTTPException, Query

from adapters.database.ports import UnitOfWork
from domain.audit import AuditAction
from interactors.api.deps import get_uow
from interactors.api.envelope import ok

router = APIRouter(tags=["audit"])

_ACTIONS = {a.value for a in AuditAction}


@router.get("/audit")
def list_audit(
    run_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    page_size: int = Query(50, ge=1, le=200),
    page_number: int = Query(1, ge=1),
    uow: UnitOfWork = Depends(get_uow),
) -> dict:
    if action is not None and action not in _ACTIONS:
        raise HTTPException(status_code=422, detail=f"action must be one of {_ACTIONS}")
    filters: dict = {}
    if run_id:
        filters["run_id"] = run_id
    if action:
        filters["action"] = action
    with uow.transaction():
        page = uow.audit_events.list(
            filters=filters, order_by="-created_at",
            page_size=page_size, page_number=page_number,
        )
    return ok(
        [e.model_dump(mode="json") for e in page.results],
        meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number},
    )
