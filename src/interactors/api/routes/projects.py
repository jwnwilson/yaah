from fastapi import Depends
from pydantic import BaseModel

from domain.models import AutonomyLevel, Project
from domain.ports import UnitOfWork
from interactors.api.crud_router import CrudRouter
from interactors.api.deps import get_uow
from interactors.api.envelope import ok


class CreateProject(BaseModel):
    name: str
    repo_url: str | None = None
    local_path: str | None = None
    autonomy: AutonomyLevel = AutonomyLevel.GATED_ALL


class UpdateProject(BaseModel):
    name: str | None = None
    team_id: str | None = None
    autonomy: AutonomyLevel | None = None


router = CrudRouter(
    repository="projects",
    response_dto=Project,
    create_schema=CreateProject,
    update_schema=UpdateProject,
    methods=("CREATE", "READ", "UPDATE", "DELETE"),
    prefix="/projects",
    tags=["projects"],
)


@router.delete("/{project_id}")
def delete_project(project_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    """Override: cascade child work items in the same transaction."""
    with uow.transaction():
        uow.projects.get(project_id)  # 404 (RecordNotFound) if absent/not owned
        uow.work_items.delete_many({"project_id": project_id})
        uow.projects.delete(project_id)
    return ok({"deleted": project_id})
