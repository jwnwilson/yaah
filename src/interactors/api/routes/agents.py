from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from adapters.database.ports import UnitOfWork
from domain.agent.models import AgentDefinition, AgentRole
from interactors.api.deps import get_uow
from interactors.api.envelope import ok

router = APIRouter(tags=["agents"])


class CreateAgent(BaseModel):
    role: AgentRole
    name: str
    model_alias: str
    persona: str = ""
    purpose: str = ""
    system_prompt: str = ""
    allowed_tools: list[str] = []
    skill_ids: list[str] = []
    mcp_server_ids: list[str] = []
    secret_ids: list[str] = []


class UpdateAgent(BaseModel):
    name: str | None = None
    model_alias: str | None = None
    persona: str | None = None
    purpose: str | None = None
    system_prompt: str | None = None
    allowed_tools: list[str] | None = None
    skill_ids: list[str] | None = None
    mcp_server_ids: list[str] | None = None
    secret_ids: list[str] | None = None


def _validate_grants(
    uow: UnitOfWork,
    skill_ids: list[str] | None,
    mcp_server_ids: list[str] | None,
    secret_ids: list[str] | None,
) -> None:
    for sid in skill_ids or []:
        uow.skills.get(sid)  # RecordNotFound -> 404 (owner-scoped)
    for mid in mcp_server_ids or []:
        uow.mcp_servers.get(mid)
    for sec in secret_ids or []:
        uow.secrets.get(sec)


@router.post("/teams/{team_id}/agents", status_code=201)
def create_agent(
    team_id: str, body: CreateAgent, uow: UnitOfWork = Depends(get_uow)
) -> dict:
    with uow.transaction():
        uow.teams.get(team_id)  # 404 if team absent / not owned
        _validate_grants(uow, body.skill_ids, body.mcp_server_ids, body.secret_ids)
        agent = AgentDefinition(team_id=team_id, **body.model_dump())
        created = uow.agents.create(agent)
    return ok(created.model_dump(mode="json"))


@router.get("/teams/{team_id}/agents")
def list_agents(
    team_id: str,
    page_size: int = Query(100, ge=1, le=200),
    page_number: int = Query(1, ge=1),
    uow: UnitOfWork = Depends(get_uow),
) -> dict:
    with uow.transaction():
        uow.teams.get(team_id)
        page = uow.agents.list(
            filters={"team_id": team_id},
            page_size=page_size,
            page_number=page_number,
            order_by="id",
        )
    return ok(
        [a.model_dump(mode="json") for a in page.results],
        meta={
            "total": page.total,
            "page_size": page.page_size,
            "page_number": page.page_number,
        },
    )


@router.get("/agents/{agent_id}")
def get_agent(agent_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        agent = uow.agents.get(agent_id)
    return ok(agent.model_dump(mode="json"))


@router.patch("/agents/{agent_id}")
def patch_agent(
    agent_id: str, body: UpdateAgent, uow: UnitOfWork = Depends(get_uow)
) -> dict:
    with uow.transaction():
        agent = uow.agents.get(agent_id)
        updates = body.model_dump(exclude_none=True)
        _validate_grants(
            uow,
            updates.get("skill_ids"),
            updates.get("mcp_server_ids"),
            updates.get("secret_ids"),
        )
        result = uow.agents.update(agent_id, agent.model_copy(update=updates))
    return ok(result.model_dump(mode="json"))


@router.delete("/agents/{agent_id}")
def delete_agent(agent_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        uow.agents.delete(agent_id)
    return ok({"deleted": agent_id})
