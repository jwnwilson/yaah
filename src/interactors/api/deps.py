from fastapi import Depends, Request

from adapters.database.uow import SqlUnitOfWork
from domain.ports import UnitOfWork
from interactors.api.auth import current_user_id


def get_uow(request: Request, user_id: str = Depends(current_user_id)) -> UnitOfWork:
    return SqlUnitOfWork(
        request.app.state.session_factory,
        required_filters={"owner_id": user_id},
    )
