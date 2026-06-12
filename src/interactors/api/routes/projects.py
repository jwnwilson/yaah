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


# Path param must be named `entity_id` to match the generated DELETE route's
# path string, so the decorator's _remove_route drops the non-cascading one.
@router.delete("/{entity_id}")
def delete_project(entity_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    """Override: cascade child work items in the same transaction."""
    with uow.transaction():
        uow.projects.get(entity_id)  # 404 (RecordNotFound) if absent/not owned
        uow.work_items.delete_many({"project_id": entity_id})
        uow.projects.delete(entity_id)
    return ok({"deleted": entity_id})
