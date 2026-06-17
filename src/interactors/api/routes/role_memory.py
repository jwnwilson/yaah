from fastapi import APIRouter, Depends, HTTPException, Query

from adapters.database.ports import UnitOfWork
from domain.agent.models import AgentRole
from interactors.api.deps import get_uow
from interactors.api.envelope import ok

router = APIRouter(tags=["role-memory"])

_ROLES = {r.value for r in AgentRole}


@router.get("/role-memory")
def list_role_memory(
    role: str = Query(...),
    project_id: str | None = Query(default=None),
    page_size: int = Query(50, ge=1, le=200),
    page_number: int = Query(1, ge=1),
    uow: UnitOfWork = Depends(get_uow),
) -> dict:
    if role not in _ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of {_ROLES}")
    filters: dict = {"role": role}
    if project_id:
        filters["project_id"] = project_id
    with uow.transaction():
        page = uow.role_memory.list(
            filters=filters, order_by="-created_at",
            page_size=page_size, page_number=page_number,
        )
    return ok(
        [e.model_dump(mode="json") for e in page.results],
        meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number},
    )
