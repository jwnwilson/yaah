from fastapi import APIRouter, Depends

from domain.models import AgentRole
from domain.ports import UnitOfWork
from domain.teams import default_team
from interactors.api.auth import current_user_id
from interactors.api.deps import get_uow
from interactors.api.envelope import ok

router = APIRouter(prefix="/teams", tags=["teams"])

_ROLE_ORDER = {role: index for index, role in enumerate(AgentRole)}


@router.post("/default", status_code=201)
def create_default(
    user_id: str = Depends(current_user_id),
    uow: UnitOfWork = Depends(get_uow),
) -> dict:
    team, agents = default_team(owner_id=user_id)
    with uow.transaction():
        uow.teams.create(team)
        stored_agents = [uow.agents.create(agent) for agent in agents]
    return ok(
        {
            "team": team.model_dump(mode="json"),
            "agents": [a.model_dump(mode="json") for a in stored_agents],
        }
    )


@router.get("")
def list_teams(uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        page = uow.teams.list()
    return ok(
        [t.model_dump(mode="json") for t in page.results],
        meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number},
    )


@router.get("/{team_id}")
def get(team_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        team = uow.teams.get(team_id)  # RecordNotFound -> 404
        agents = sorted(
            uow.agents.list(filters={"team_id": team_id}).results,
            key=lambda a: _ROLE_ORDER[a.role],
        )
    return ok(
        {
            "team": team.model_dump(mode="json"),
            "agents": [a.model_dump(mode="json") for a in agents],
        }
    )
