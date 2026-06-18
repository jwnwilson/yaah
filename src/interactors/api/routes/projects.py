from fastapi import Depends
from pydantic import BaseModel

from adapters.database.ports import UnitOfWork
from domain.projects import AutonomyLevel, Project
from interactors.api.deps import get_uow, temporal_client
from interactors.api.deps import settings as get_settings
from interactors.api.envelope import ok
from interactors.scheduling import reconcile_project
from interactors.temporal.client import TemporalRunClient
from lib.crud_router import CrudRouter


class CreateProject(BaseModel):
    name: str
    repo_url: str | None = None
    local_path: str | None = None
    autonomy: AutonomyLevel = AutonomyLevel.GATED_ALL


class UpdateProject(BaseModel):
    name: str | None = None
    team_id: str | None = None
    autonomy: AutonomyLevel | None = None
    max_concurrent_runs: int | None = None


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


@router.patch("/{entity_id}")
def update_project(
    entity_id: str, body: UpdateProject,
    uow: UnitOfWork = Depends(get_uow),
    temporal: TemporalRunClient = Depends(temporal_client),
    settings=Depends(get_settings),
) -> dict:
    """Override: persist fields and, when the concurrency cap changes, reconcile to pull work."""
    run_inputs: list[dict] = []
    with uow.transaction():
        project = uow.projects.get(entity_id)  # 404 if absent/not owned
        updated = uow.projects.update(
            entity_id, project.model_copy(update=body.model_dump(exclude_none=True))
        )
        if body.max_concurrent_runs is not None:
            run_inputs = reconcile_project(uow, settings, entity_id)
    for ri in run_inputs:
        temporal.start_run_workflow(ri, "OrchestratorWorkflow")
    return ok(updated.model_dump(mode="json"))
