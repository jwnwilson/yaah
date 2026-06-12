from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from adapters.database.stores import SqlProjectStore, SqlWorkItemStore
from domain.models import WorkItem, WorkItemKind, WorkItemStatus, utc_now
from domain.transitions import InvalidTransition, validate_transition
from interactors.api.auth import current_user_id
from interactors.api.deps import project_store, work_item_store
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
def create(
    project_id: str,
    body: CreateWorkItem,
    user_id: str = Depends(current_user_id),
    projects: SqlProjectStore = Depends(project_store),
    store: SqlWorkItemStore = Depends(work_item_store),
) -> dict:
    if not projects.get(project_id, owner_id=user_id):
        raise HTTPException(status_code=404, detail="project not found")
    try:
        item = WorkItem(project_id=project_id, owner_id=user_id, **body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ok(store.add(item).model_dump(mode="json"))


@router.get("/projects/{project_id}/work-items")
def list_items(
    project_id: str,
    kind: WorkItemKind | None = None,
    status: WorkItemStatus | None = None,
    parent_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    user_id: str = Depends(current_user_id),
    projects: SqlProjectStore = Depends(project_store),
    store: SqlWorkItemStore = Depends(work_item_store),
) -> dict:
    if not projects.get(project_id, owner_id=user_id):
        raise HTTPException(status_code=404, detail="project not found")
    items = store.list(
        project_id, kind=kind, status=status, parent_id=parent_id, limit=limit, offset=offset
    )
    return ok([i.model_dump(mode="json") for i in items], meta={"limit": limit, "offset": offset})


def _get_or_404(store: SqlWorkItemStore, item_id: str) -> WorkItem:
    item = store.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="work item not found")
    return item


@router.patch("/work-items/{item_id}")
def patch(
    item_id: str,
    body: UpdateWorkItem,
    store: SqlWorkItemStore = Depends(work_item_store),
) -> dict:
    item = _get_or_404(store, item_id)
    updated = item.model_copy(
        update={**body.model_dump(exclude_none=True), "updated_at": utc_now()}
    )
    return ok(store.update(updated).model_dump(mode="json"))


@router.post("/work-items/{item_id}/status")
def set_status(
    item_id: str,
    body: SetStatus,
    store: SqlWorkItemStore = Depends(work_item_store),
) -> dict:
    item = _get_or_404(store, item_id)
    try:
        validate_transition(item.status, body.status)
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    updated = item.model_copy(update={"status": body.status, "updated_at": utc_now()})
    return ok(store.update(updated).model_dump(mode="json"))


@router.delete("/work-items/{item_id}")
def delete(item_id: str, store: SqlWorkItemStore = Depends(work_item_store)) -> dict:
    _get_or_404(store, item_id)
    store.delete(item_id)
    return ok({"deleted": item_id})
