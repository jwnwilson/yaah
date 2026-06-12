from fastapi import APIRouter, Depends, HTTPException

from domain.models import Run, WorkItemKind, WorkItemStatus, utc_now
from domain.ports import UnitOfWork
from domain.transitions import validate_transition
from interactors.api.deps import get_uow
from interactors.api.envelope import ok

router = APIRouter(tags=["runs"])


@router.post("/work-items/{task_id}/runs", status_code=201)
def start_run(task_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        task = uow.work_items.get(task_id)  # RecordNotFound -> 404 (owner-scoped)
        if task.kind != WorkItemKind.TASK:
            raise HTTPException(status_code=404, detail="task not found")
        if task.status != WorkItemStatus.READY:
            raise HTTPException(status_code=409, detail=f"task is {task.status}, must be ready")
        # Honour the central state machine for the actual transition we apply.
        validate_transition(task.status, WorkItemStatus.IN_PROGRESS)  # InvalidTransition -> 409
        project = uow.projects.get(task.project_id)
        if not project.team_id:
            raise HTTPException(status_code=409, detail="project has no team assigned")
        run = uow.runs.create(
            Run(owner_id=project.owner_id, task_id=task_id, team_id=project.team_id)
        )
        uow.work_items.update(
            task_id,
            task.model_copy(update={"status": WorkItemStatus.IN_PROGRESS, "updated_at": utc_now()}),
        )
    # run insert + task transition commit or roll back together (closes the A1 atomicity gap)
    return ok(run.model_dump(mode="json"))


@router.get("/work-items/{task_id}/runs")
def list_runs(task_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        uow.work_items.get(task_id)  # 404 for unknown task (unifies list semantics)
        page = uow.runs.list(filters={"task_id": task_id}, order_by="-created_at")
    return ok(
        [r.model_dump(mode="json") for r in page.results],
        meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number},
    )


@router.get("/runs/{run_id}")
def get_run(run_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        run = uow.runs.get(run_id)  # owner-scoped -> cross-tenant 404
    return ok(run.model_dump(mode="json"))
