from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from domain.models import WorkItem, WorkItemKind, WorkItemStatus, utc_now
from domain.ports import UnitOfWork
from domain.transitions import validate_transition
from interactors.api.deps import get_uow
from interactors.api.envelope import ok

router = APIRouter(tags=["work-items"])


class CreateWorkItem(BaseModel):
    kind: WorkItemKind
    title: str
    body: str = ""
    parent_id: str | None = None
    acceptance_criteria: list[str] = []


class UpdateWorkItem(BaseModel):
    title: str | None = None
    body: str | None = None
    acceptance_criteria: list[str] | None = None


class SetStatus(BaseModel):
    status: WorkItemStatus


@router.post("/projects/{project_id}/work-items", status_code=201)
def create(project_id: str, body: CreateWorkItem, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        project = uow.projects.get(project_id)  # RecordNotFound -> 404
        item = WorkItem(project_id=project_id, owner_id=project.owner_id, **body.model_dump())
        created = uow.work_items.create(item)
    return ok(created.model_dump(mode="json"))


@router.get("/projects/{project_id}/work-items")
def list_items(
    project_id: str,
    kind: WorkItemKind | None = None,
    status: WorkItemStatus | None = None,
    parent_id: str | None = None,
    page_size: int = Query(100, ge=1, le=200),
    page_number: int = Query(1, ge=1),
    uow: UnitOfWork = Depends(get_uow),
) -> dict:
    filters: dict = {"project_id": project_id}
    if kind:
        filters["kind"] = kind
    if status:
        filters["status"] = status
    if parent_id:
        filters["parent_id"] = parent_id
    with uow.transaction():
        uow.projects.get(project_id)  # RecordNotFound -> 404
        page = uow.work_items.list(
            filters=filters,
            page_size=page_size,
            page_number=page_number,
            order_by="created_at",
        )
    return ok(
        [i.model_dump(mode="json") for i in page.results],
        meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number},
    )


@router.patch("/work-items/{item_id}")
def patch(item_id: str, body: UpdateWorkItem, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        item = uow.work_items.get(item_id)  # owner-scoped: cross-tenant -> 404
        updated = item.model_copy(
            update={**body.model_dump(exclude_none=True), "updated_at": utc_now()}
        )
        result = uow.work_items.update(item_id, updated)
    return ok(result.model_dump(mode="json"))


@router.post("/work-items/{item_id}/status")
def set_status(item_id: str, body: SetStatus, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        item = uow.work_items.get(item_id)
        validate_transition(item.status, body.status)  # InvalidTransition -> 409
        updated = item.model_copy(update={"status": body.status, "updated_at": utc_now()})
        result = uow.work_items.update(item_id, updated)
    return ok(result.model_dump(mode="json"))


@router.delete("/work-items/{item_id}")
def delete(item_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        uow.work_items.delete(item_id)  # get+delete, owner-scoped
    return ok({"deleted": item_id})
