from fastapi import Depends, Request

from adapters.database.ports import UnitOfWork
from adapters.database.uow import SqlUnitOfWork
from interactors.api.auth import current_user_id
from interactors.temporal.client import TemporalRunClient
from interactors.temporal.config import TemporalConfig


def get_uow(request: Request, user_id: str = Depends(current_user_id)) -> UnitOfWork:
    return SqlUnitOfWork(
        request.app.state.session_factory,
        required_filters={"owner_id": user_id},
    )


def temporal_client(request: Request) -> TemporalRunClient:
    return TemporalRunClient(TemporalConfig.from_settings(request.app.state.settings))


def settings(request: Request):
    return request.app.state.settings


def cipher(request: Request):
    from adapters.secrets.cipher import FernetCipher

    key = request.app.state.settings.secret_key
    return FernetCipher(key) if key else None
