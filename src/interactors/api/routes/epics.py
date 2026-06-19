from fastapi import APIRouter, Depends

from adapters.database.ports import UnitOfWork
from domain.projects import WorkItemKind, build_backlog, build_epic_board
from domain.runs import RunStatus
from interactors.api.deps import get_uow
from interactors.api.envelope import ok

router = APIRouter(tags=["epics"])

_NON_TERMINAL = [
    RunStatus.PENDING.value, RunStatus.RUNNING.value,
    RunStatus.AWAITING_APPROVAL.value, RunStatus.BLOCKED.value,
]


@router.get("/projects/{project_id}/backlog")
def backlog(project_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        project = uow.projects.get(project_id)  # 404
        epics = uow.work_items.list(
            filters={"project_id": project_id, "kind": WorkItemKind.EPIC},
            page_size=500, order_by="created_at").results
        features = uow.work_items.list(
            filters={"project_id": project_id, "kind": WorkItemKind.FEATURE},
            page_size=500).results
        tasks = uow.work_items.list(
            filters={"project_id": project_id, "kind": WorkItemKind.TASK},
            page_size=1000).results
        task_ids = [t.id for t in tasks]
        in_flight_task_ids: set[str] = set()
        if task_ids:
            runs = uow.runs.list(
                filters={"task_id__in": task_ids, "status__in": _NON_TERMINAL},
                page_size=1000).results
            in_flight_task_ids = {r.task_id for r in runs}
        view = build_backlog(
            epics=epics, features=features, tasks=tasks,
            in_flight_task_ids=in_flight_task_ids,
            max_concurrent_runs=project.max_concurrent_runs,
        )
    return ok(view.model_dump(mode="json"))


@router.get("/projects/{project_id}/epics/{epic_id}/board")
def epic_board(
    project_id: str, epic_id: str, uow: UnitOfWork = Depends(get_uow)
) -> dict:
    with uow.transaction():
        uow.projects.get(project_id)  # RecordNotFound -> 404
        epic = uow.work_items.get(epic_id)  # owner-scoped; RecordNotFound -> 404
        features = uow.work_items.list(
            filters={"project_id": project_id, "parent_id": epic_id, "kind": WorkItemKind.FEATURE},
            page_size=200,
            order_by="created_at",
        ).results
        parent_ids = [epic_id, *(f.id for f in features)]
        tasks = [
            t
            for parent_id in parent_ids
            for t in uow.work_items.list(
                filters={
                    "project_id": project_id,
                    "parent_id": parent_id,
                    "kind": WorkItemKind.TASK,
                },
                page_size=200,
                order_by="created_at",
            ).results
        ]
        board = build_epic_board(epic, features, tasks)
    return ok(board.model_dump(mode="json"))
