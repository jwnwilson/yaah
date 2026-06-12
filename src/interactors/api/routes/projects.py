from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from adapters.database.stores import SqlProjectStore
from domain.models import AutonomyLevel, Project
from interactors.api.auth import current_user_id
from interactors.api.deps import project_store
from interactors.api.envelope import ok

router = APIRouter(prefix="/projects", tags=["projects"])


class CreateProject(BaseModel):
    name: str
    repo_url: str | None = None
    local_path: str | None = None
    autonomy: AutonomyLevel = AutonomyLevel.GATED_ALL


class UpdateProject(BaseModel):
    name: str | None = None
    team_id: str | None = None
    autonomy: AutonomyLevel | None = None


@router.post("", status_code=201)
def create(
    body: CreateProject,
    user_id: str = Depends(current_user_id),
    store: SqlProjectStore = Depends(project_store),
) -> dict:
    try:
        project = Project(owner_id=user_id, **body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ok(store.add(project).model_dump(mode="json"))


@router.get("")
def list_projects(
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(current_user_id),
    store: SqlProjectStore = Depends(project_store),
) -> dict:
    items = store.list(user_id, limit=limit, offset=offset)
    return ok([p.model_dump(mode="json") for p in items], meta={"limit": limit, "offset": offset})


def _get_or_404(store: SqlProjectStore, project_id: str, user_id: str) -> Project:
    project = store.get(project_id, owner_id=user_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    return project


@router.get("/{project_id}")
def get(
    project_id: str,
    user_id: str = Depends(current_user_id),
    store: SqlProjectStore = Depends(project_store),
) -> dict:
    return ok(_get_or_404(store, project_id, user_id).model_dump(mode="json"))


@router.patch("/{project_id}")
def patch(
    project_id: str,
    body: UpdateProject,
    user_id: str = Depends(current_user_id),
    store: SqlProjectStore = Depends(project_store),
) -> dict:
    project = _get_or_404(store, project_id, user_id)
    updated = project.model_copy(update=body.model_dump(exclude_none=True))
    return ok(store.update(updated).model_dump(mode="json"))


@router.delete("/{project_id}")
def delete(
    project_id: str,
    user_id: str = Depends(current_user_id),
    store: SqlProjectStore = Depends(project_store),
) -> dict:
    _get_or_404(store, project_id, user_id)
    store.delete(project_id, owner_id=user_id)
    return ok({"deleted": project_id})
