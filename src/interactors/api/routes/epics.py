from fastapi import APIRouter, Depends

from adapters.database.ports import UnitOfWork
from domain.projects import WorkItemKind, build_epic_board
from interactors.api.deps import get_uow
from interactors.api.envelope import ok

router = APIRouter(tags=["epics"])


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
