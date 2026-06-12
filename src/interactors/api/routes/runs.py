from fastapi import APIRouter, Depends, HTTPException

from adapters.database.stores import SqlProjectStore, SqlRunStore, SqlWorkItemStore
from domain.models import Run, WorkItemKind, WorkItemStatus, utc_now
from interactors.api.auth import current_user_id
from interactors.api.deps import project_store, run_store, work_item_store
from interactors.api.envelope import ok

router = APIRouter(tags=["runs"])


@router.post("/work-items/{task_id}/runs", status_code=201)
def start_run(
    task_id: str,
    user_id: str = Depends(current_user_id),
    items: SqlWorkItemStore = Depends(work_item_store),
    projects: SqlProjectStore = Depends(project_store),
    store: SqlRunStore = Depends(run_store),
) -> dict:
    task = items.get(task_id)
    if not task or task.kind != WorkItemKind.TASK:
        raise HTTPException(status_code=404, detail="task not found")
    if task.status != WorkItemStatus.READY:
        raise HTTPException(status_code=409, detail=f"task is {task.status}, must be ready")
    project = projects.get(task.project_id, owner_id=user_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    if not project.team_id:
        raise HTTPException(status_code=409, detail="project has no team assigned")

    run = store.add(Run(task_id=task_id, team_id=project.team_id, owner_id=project.owner_id))
    items.update(
        task.model_copy(update={"status": WorkItemStatus.IN_PROGRESS, "updated_at": utc_now()})
    )
    return ok(run.model_dump(mode="json"))


@router.get("/work-items/{task_id}/runs")
def list_runs(task_id: str, store: SqlRunStore = Depends(run_store)) -> dict:
    return ok([r.model_dump(mode="json") for r in store.list_for_task(task_id)])


@router.get("/runs/{run_id}")
def get_run(run_id: str, store: SqlRunStore = Depends(run_store)) -> dict:
    run = store.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return ok(run.model_dump(mode="json"))
