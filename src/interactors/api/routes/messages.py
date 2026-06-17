from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from adapters.database.ports import UnitOfWork
from domain.base import utc_now
from domain.messages import Message, MessageKind, MessageRecipientKind, MessageSenderKind
from interactors.api.auth import current_user_id
from interactors.api.deps import get_uow
from interactors.api.envelope import ok

router = APIRouter(tags=["messages"])


def _box_filters(box: str | None) -> dict:
    """box='me' -> the user's mailbox; box=<agentId> -> that agent's mailbox."""
    if box == "me":
        return {"recipient_kind": "user"}
    if box:
        return {"recipient_kind": "agent", "recipient_agent_id": box}
    return {}


def _status_filters(status: str | None) -> dict:
    if status == "unread":
        return {"read_at__isnull": True}
    if status == "read":
        return {"read_at__isnull": False}
    return {}


@router.get("/messages")
def list_messages(
    box: str | None = Query(default=None),
    sender: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page_size: int = Query(default=50),
    page_number: int = Query(default=1),
    uow: UnitOfWork = Depends(get_uow),
) -> dict:
    filters = {**_box_filters(box), **_status_filters(status)}
    if sender:
        filters["sender_agent_id"] = sender
    with uow.transaction():
        page = uow.messages.list(filters=filters, page_size=page_size,
                                 page_number=page_number, order_by="-created_at")
    return ok(
        [m.model_dump(mode="json") for m in page.results],
        meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number},
    )


@router.get("/messages/unread-count")
def unread_count(box: str | None = Query(default=None),
                 uow: UnitOfWork = Depends(get_uow)) -> dict:
    filters = {**_box_filters(box), "read_at__isnull": True}
    with uow.transaction():
        page = uow.messages.list(filters=filters, page_size=1)
    return ok({"count": page.total})


class PatchMessage(BaseModel):
    read: bool | None = None


@router.patch("/messages/{message_id}")
def patch_message(message_id: str, body: PatchMessage,
                  uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        m = uow.messages.get(message_id)  # owner-scoped: cross-tenant -> 404
        updates: dict = {}
        if body.read and m.read_at is None:
            updates["read_at"] = utc_now()
        result = uow.messages.update(message_id, m.model_copy(update=updates))
    return ok(result.model_dump(mode="json"))


class SendMessage(BaseModel):
    recipient_kind: MessageRecipientKind
    recipient_agent_id: str | None = None
    kind: MessageKind = MessageKind.CHAT
    subject: str = ""
    body: str
    run_id: str | None = None
    work_item_id: str | None = None
    project_id: str | None = None


@router.post("/messages", status_code=201)
def send_message(body: SendMessage, user_id: str = Depends(current_user_id),
                 uow: UnitOfWork = Depends(get_uow)) -> dict:
    msg = Message(owner_id=user_id, sender_kind=MessageSenderKind.USER, **body.model_dump())
    with uow.transaction():
        created = uow.messages.create(msg)
    return ok(created.model_dump(mode="json"))
