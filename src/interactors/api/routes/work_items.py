from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from adapters.database.ports import UnitOfWork
from domain.base import utc_now
from domain.projects import WorkItem, WorkItemKind, WorkItemStatus
from domain.transitions import validate_transition
from interactors.api.deps import get_uow, temporal_client
from interactors.api.deps import settings as get_settings
from interactors.api.envelope import ok
from interactors.scheduling import reconcile_project
from interactors.temporal.client import TemporalRunClient

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
    assignee_agent_id: str | None = None


class SetStatus(BaseModel):
    status: WorkItemStatus


def _load_activatable(uow: UnitOfWork, project_id: str, item_id: str) -> WorkItem:
    """An epic or feature in this project — the kinds that can be active (on the board)."""
    uow.projects.get(project_id)  # RecordNotFound -> 404
    item = uow.work_items.get(item_id)  # owner-scoped
    if item.project_id != project_id or item.kind not in (WorkItemKind.EPIC, WorkItemKind.FEATURE):
        raise HTTPException(status_code=404, detail="epic or feature not found")
    return item


def _set_active(uow: UnitOfWork, item: WorkItem, active: bool) -> WorkItem:
    """Set active on an epic/feature; activating or deactivating an epic cascades to all of
    its features so the board and backlog stay in sync."""
    updated = uow.work_items.update(
        item.id, item.model_copy(update={"active": active, "updated_at": utc_now()})
    )
    if item.kind == WorkItemKind.EPIC:
        features = uow.work_items.list(
            filters={"parent_id": item.id, "kind": WorkItemKind.FEATURE}, page_size=500
        ).results
        for f in features:
            if f.active != active:
                uow.work_items.update(
                    f.id, f.model_copy(update={"active": active, "updated_at": utc_now()})
                )
    return updated


@router.post("/projects/{project_id}/work-items/{item_id}/activate")
def activate_item(
    project_id: str, item_id: str,
    uow: UnitOfWork = Depends(get_uow),
    temporal: TemporalRunClient = Depends(temporal_client),
    settings=Depends(get_settings),
) -> dict:
    """Activate an epic or feature (move it onto the board) and auto-start its ready tasks."""
    with uow.transaction():
        item = _set_active(uow, _load_activatable(uow, project_id, item_id), True)
        run_inputs = reconcile_project(uow, settings, project_id)
    for ri in run_inputs:
        temporal.start_run_workflow(ri, "OrchestratorWorkflow")
    return ok(item.model_dump(mode="json"))


@router.post("/projects/{project_id}/work-items/{item_id}/deactivate")
def deactivate_item(
    project_id: str, item_id: str, uow: UnitOfWork = Depends(get_uow)
) -> dict:
    """Deactivate an epic or feature (move it back to the backlog). In-flight runs continue."""
    with uow.transaction():
        item = _set_active(uow, _load_activatable(uow, project_id, item_id), False)
    return ok(item.model_dump(mode="json"))


class ReorderItems(BaseModel):
    parent_id: str | None = None
    ordered_ids: list[str]


def _sibling_count(
    uow: UnitOfWork, project_id: str, kind: WorkItemKind, parent_id: str | None
) -> int:
    """How many same-kind siblings already exist under this parent (drives append position)."""
    if parent_id:
        filters = {"parent_id": parent_id, "kind": kind}
    else:
        filters = {"project_id": project_id, "kind": kind}
    return uow.work_items.list(filters=filters, page_size=1).total


def _descendant_ids(uow: UnitOfWork, item: WorkItem) -> list[str]:
    """Ids of everything beneath an item: a feature's tasks, or an epic's features +
    those features' tasks + the epic's direct tasks. Tasks have no descendants."""
    if item.kind == WorkItemKind.TASK:
        return []
    children = uow.work_items.list(filters={"parent_id": item.id}, page_size=1000).results
    ids = [c.id for c in children]
    if item.kind == WorkItemKind.EPIC:
        feature_ids = [c.id for c in children if c.kind == WorkItemKind.FEATURE]
        if feature_ids:
            grand = uow.work_items.list(
                filters={"parent_id__in": feature_ids}, page_size=1000
            ).results
            ids += [g.id for g in grand]
    return ids


@router.post("/projects/{project_id}/work-items", status_code=201)
def create(project_id: str, body: CreateWorkItem, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        project = uow.projects.get(project_id)  # RecordNotFound -> 404
        position = _sibling_count(uow, project_id, body.kind, body.parent_id)
        item = WorkItem(
            project_id=project_id, owner_id=project.owner_id, position=position, **body.model_dump()
        )
        created = uow.work_items.create(item)
    return ok(created.model_dump(mode="json"))


@router.post("/projects/{project_id}/work-items/reorder")
def reorder(project_id: str, body: ReorderItems, uow: UnitOfWork = Depends(get_uow)) -> dict:
    """Set position = index for the given sibling ids (all must share parent_id + project)."""
    with uow.transaction():
        uow.projects.get(project_id)  # RecordNotFound -> 404
        for index, item_id in enumerate(body.ordered_ids):
            item = uow.work_items.get(item_id)  # owner-scoped
            if item.project_id != project_id or item.parent_id != body.parent_id:
                raise HTTPException(status_code=400, detail="item is not a sibling in this parent")
            uow.work_items.update(
                item_id, item.model_copy(update={"position": index, "updated_at": utc_now()})
            )
    return ok({"reordered": len(body.ordered_ids)})


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


@router.get("/work-items/{item_id}")
def get_item(item_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        item = uow.work_items.get(item_id)
    return ok(item.model_dump(mode="json"))


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
def set_status(
    item_id: str, body: SetStatus,
    uow: UnitOfWork = Depends(get_uow),
    temporal: TemporalRunClient = Depends(temporal_client),
    settings=Depends(get_settings),
) -> dict:
    run_inputs: list[dict] = []
    with uow.transaction():
        item = uow.work_items.get(item_id)
        validate_transition(item.status, body.status)  # InvalidTransition -> 409
        updated = item.model_copy(update={"status": body.status, "updated_at": utc_now()})
        result = uow.work_items.update(item_id, updated)
        if body.status == WorkItemStatus.READY and item.kind == WorkItemKind.TASK:
            run_inputs = reconcile_project(uow, settings, item.project_id)
    for ri in run_inputs:
        temporal.start_run_workflow(ri, "OrchestratorWorkflow")
    return ok(result.model_dump(mode="json"))


@router.delete("/work-items/{item_id}")
def delete(item_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    """Cascade delete: removes the item and all of its descendants."""
    with uow.transaction():
        item = uow.work_items.get(item_id)  # RecordNotFound -> 404
        descendants = _descendant_ids(uow, item)
        for d in descendants:
            uow.work_items.delete(d)
        uow.work_items.delete(item_id)
    return ok({"deleted": item_id, "removed": len(descendants) + 1})
