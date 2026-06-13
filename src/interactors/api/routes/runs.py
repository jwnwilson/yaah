from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from adapters.database.ports import UnitOfWork
from domain.models import Run, RunStatus, WorkItemKind, WorkItemStatus, utc_now
from domain.transitions import validate_transition
from interactors.api.deps import get_uow, temporal_client
from interactors.api.envelope import ok
from interactors.temporal.client import TemporalRunClient

router = APIRouter(tags=["runs"])


@router.post("/work-items/{task_id}/runs", status_code=201)
def start_run(
    task_id: str,
    uow: UnitOfWork = Depends(get_uow),
    temporal: TemporalRunClient = Depends(temporal_client),
) -> dict:
    with uow.transaction():
        task = uow.work_items.get(task_id)
        if task.kind != WorkItemKind.TASK:
            raise HTTPException(status_code=404, detail="task not found")
        if task.status != WorkItemStatus.READY:
            raise HTTPException(status_code=409, detail=f"task is {task.status}, must be ready")
        validate_transition(task.status, WorkItemStatus.IN_PROGRESS)
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
        run_input = {
            "run_id": run.id,
            "owner_id": run.owner_id,
            "task_id": task_id,
            "autonomy": project.autonomy,
            "task_title": task.title,
            "acceptance_criteria": task.acceptance_criteria,
        }
    temporal.start_run_workflow(run_input)  # after commit: run row exists for the worker
    return ok(run.model_dump(mode="json"))


@router.get("/work-items/{task_id}/runs")
def list_runs(task_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        uow.work_items.get(task_id)
        page = uow.runs.list(filters={"task_id": task_id}, order_by="-created_at")
    return ok(
        [r.model_dump(mode="json") for r in page.results],
        meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number},
    )


@router.get("/runs/{run_id}")
def get_run(run_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        run = uow.runs.get(run_id)
    return ok(run.model_dump(mode="json"))


@router.get("/runs/{run_id}/events")
def list_run_events(run_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        uow.runs.get(run_id)  # 404 if unknown / cross-tenant
        page = uow.run_events.list(filters={"run_id": run_id}, order_by="created_at", page_size=200)
    return ok(
        [e.model_dump(mode="json") for e in page.results],
        meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number},
    )


def _signal(
    run_id: str,
    name: str,
    *,
    require_gate: bool,
    uow: UnitOfWork,
    temporal: TemporalRunClient,
) -> dict:
    with uow.transaction():
        run = uow.runs.get(run_id)
        if require_gate and run.status != RunStatus.AWAITING_APPROVAL:
            raise HTTPException(
                status_code=409, detail=f"run is {run.status}, not awaiting approval"
            )
        terminal = (RunStatus.DONE, RunStatus.FAILED, RunStatus.CANCELLED)
        if not require_gate and run.status in terminal:
            raise HTTPException(status_code=409, detail=f"run is terminal ({run.status})")
    temporal.signal(run_id, name)
    return run.model_dump(mode="json")


@router.post("/runs/{run_id}/approve", status_code=202)
def approve_run(
    run_id: str,
    uow: UnitOfWork = Depends(get_uow),
    temporal: TemporalRunClient = Depends(temporal_client),
) -> dict:
    return ok(_signal(run_id, "approve", require_gate=True, uow=uow, temporal=temporal))


@router.post("/runs/{run_id}/reject", status_code=202)
def reject_run(
    run_id: str,
    uow: UnitOfWork = Depends(get_uow),
    temporal: TemporalRunClient = Depends(temporal_client),
) -> dict:
    return ok(_signal(run_id, "reject", require_gate=True, uow=uow, temporal=temporal))


@router.post("/runs/{run_id}/cancel", status_code=202)
def cancel_run(
    run_id: str,
    uow: UnitOfWork = Depends(get_uow),
    temporal: TemporalRunClient = Depends(temporal_client),
) -> dict:
    return ok(_signal(run_id, "cancel", require_gate=False, uow=uow, temporal=temporal))


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
