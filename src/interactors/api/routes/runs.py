from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from adapters.database.ports import UnitOfWork
from domain.models import Run, RunStatus, WorkItemKind, WorkItemStatus, utc_now
from domain.run_transitions import validate_run_transition
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


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        run = uow.runs.get(run_id)
        validate_run_transition(run.status, RunStatus.CANCELLED)
        result = uow.runs.update(run_id, run.model_copy(update={"status": RunStatus.CANCELLED}))
    return ok(result.model_dump(mode="json"))


def _gate(run_id: str, dst: RunStatus, uow: UnitOfWork) -> dict:
    with uow.transaction():
        run = uow.runs.get(run_id)
        validate_run_transition(run.status, dst)
        result = uow.runs.update(run_id, run.model_copy(update={"status": dst}))
    return ok(result.model_dump(mode="json"))


@router.post("/runs/{run_id}/approve")
def approve_run(run_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    return _gate(run_id, RunStatus.DONE, uow)


@router.post("/runs/{run_id}/reject")
def reject_run(run_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    return _gate(run_id, RunStatus.FAILED, uow)


class UpdateRun(BaseModel):
    stage: str | None = None
    branch: str | None = None
    pr_url: str | None = None


@router.patch("/runs/{run_id}")
def patch_run(run_id: str, body: UpdateRun, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        run = uow.runs.get(run_id)
        result = uow.runs.update(run_id, run.model_copy(update=body.model_dump(exclude_none=True)))
    return ok(result.model_dump(mode="json"))
