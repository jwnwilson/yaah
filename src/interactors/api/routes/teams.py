from fastapi import APIRouter, Depends, HTTPException

from adapters.database.stores import SqlTeamStore
from domain.teams import default_team
from interactors.api.auth import current_user_id
from interactors.api.deps import team_store
from interactors.api.envelope import ok

router = APIRouter(prefix="/teams", tags=["teams"])


@router.post("/default", status_code=201)
def create_default(
    user_id: str = Depends(current_user_id),
    store: SqlTeamStore = Depends(team_store),
) -> dict:
    team, agents = default_team(owner_id=user_id)
    store.add(team, agents)
    return ok(
        {
            "team": team.model_dump(mode="json"),
            "agents": [a.model_dump(mode="json") for a in agents],
        }
    )


@router.get("")
def list_teams(
    user_id: str = Depends(current_user_id),
    store: SqlTeamStore = Depends(team_store),
) -> dict:
    return ok([t.model_dump(mode="json") for t in store.list(user_id)])


@router.get("/{team_id}")
def get(
    team_id: str,
    user_id: str = Depends(current_user_id),
    store: SqlTeamStore = Depends(team_store),
) -> dict:
    team = store.get(team_id, owner_id=user_id)
    if not team:
        raise HTTPException(status_code=404, detail="team not found")
    agents = store.agents(team_id)
    return ok(
        {
            "team": team.model_dump(mode="json"),
            "agents": [a.model_dump(mode="json") for a in agents],
        }
    )
