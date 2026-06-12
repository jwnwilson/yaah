from fastapi import Depends, Request

from adapters.database.stores import SqlProjectStore, SqlRunStore, SqlTeamStore, SqlWorkItemStore
from adapters.database.uow import SqlUnitOfWork
from domain.ports import UnitOfWork
from interactors.api.auth import current_user_id


def get_uow(request: Request, user_id: str = Depends(current_user_id)) -> UnitOfWork:
    return SqlUnitOfWork(
        request.app.state.session_factory,
        required_filters={"owner_id": user_id},
    )


def project_store(request: Request) -> SqlProjectStore:
    return SqlProjectStore(request.app.state.session_factory)


def work_item_store(request: Request) -> SqlWorkItemStore:
    return SqlWorkItemStore(request.app.state.session_factory)


def team_store(request: Request) -> SqlTeamStore:
    return SqlTeamStore(request.app.state.session_factory)


def run_store(request: Request) -> SqlRunStore:
    return SqlRunStore(request.app.state.session_factory)
