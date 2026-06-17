from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from adapters.database.ports import UnitOfWork
from domain.agent.capability_grants import McpServer, Secret, Skill
from interactors.api.auth import current_user_id
from interactors.api.deps import cipher, get_uow
from interactors.api.envelope import ok
from lib.crud_router import CrudRouter


class CreateSkill(BaseModel):
    name: str
    description: str = ""
    source: str = ""


class UpdateSkill(BaseModel):
    name: str | None = None
    description: str | None = None
    source: str | None = None


class CreateMcpServer(BaseModel):
    name: str
    transport: Literal["stdio", "http"] = "stdio"
    command_or_url: str = ""
    tool_allowlist: list[str] = []


class UpdateMcpServer(BaseModel):
    name: str | None = None
    transport: Literal["stdio", "http"] | None = None
    command_or_url: str | None = None
    tool_allowlist: list[str] | None = None


class CreateSecret(BaseModel):
    name: str
    description: str = ""


class UpdateSecret(BaseModel):
    name: str | None = None
    description: str | None = None


class SetSecretValue(BaseModel):
    value: str


skills_router = CrudRouter(
    repository="skills",
    response_dto=Skill,
    create_schema=CreateSkill,
    update_schema=UpdateSkill,
    methods=("CREATE", "READ", "UPDATE", "DELETE"),
    prefix="/skills",
    tags=["capabilities"],
)

mcp_router = CrudRouter(
    repository="mcp_servers",
    response_dto=McpServer,
    create_schema=CreateMcpServer,
    update_schema=UpdateMcpServer,
    methods=("CREATE", "READ", "UPDATE", "DELETE"),
    prefix="/mcp-servers",
    tags=["capabilities"],
)


def _secret_read(s: Secret) -> dict:
    d = s.model_dump(mode="json")
    d.pop("encrypted_value", None)
    d["has_value"] = s.encrypted_value is not None
    return d


secrets_router = APIRouter(prefix="/secrets", tags=["capabilities"])


@secrets_router.post("", status_code=201)
def create_secret(
    body: CreateSecret,
    user_id: str = Depends(current_user_id),
    uow: UnitOfWork = Depends(get_uow),
) -> dict:
    with uow.transaction():
        created = uow.secrets.create(Secret(owner_id=user_id, **body.model_dump()))
    return ok(_secret_read(created))


@secrets_router.get("")
def list_secrets(
    page_size: int = Query(100, ge=1, le=200),
    page_number: int = Query(1, ge=1),
    uow: UnitOfWork = Depends(get_uow),
) -> dict:
    with uow.transaction():
        page = uow.secrets.list(page_size=page_size, page_number=page_number)
    return ok(
        [_secret_read(s) for s in page.results],
        meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number},
    )


@secrets_router.get("/{secret_id}")
def get_secret(secret_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        s = uow.secrets.get(secret_id)
    return ok(_secret_read(s))


@secrets_router.patch("/{secret_id}")
def patch_secret(
    secret_id: str,
    body: UpdateSecret,
    uow: UnitOfWork = Depends(get_uow),
) -> dict:
    with uow.transaction():
        s = uow.secrets.get(secret_id)
        updated = s.model_copy(update=body.model_dump(exclude_none=True))
        result = uow.secrets.update(secret_id, updated)
    return ok(_secret_read(result))


@secrets_router.delete("/{secret_id}")
def delete_secret(secret_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        uow.secrets.delete(secret_id)
    return ok({"deleted": secret_id})


@secrets_router.put("/{secret_id}/value")
def set_secret_value(
    secret_id: str,
    body: SetSecretValue,
    uow: UnitOfWork = Depends(get_uow),
    c=Depends(cipher),
) -> dict:
    if c is None:
        raise HTTPException(status_code=503, detail="secret encryption key not configured")
    with uow.transaction():
        s = uow.secrets.get(secret_id)
        result = uow.secrets.update(
            secret_id,
            s.model_copy(update={"encrypted_value": c.encrypt(body.value)}),
        )
    return ok(_secret_read(result))
