from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from adapters.database.ports import UnitOfWork
from domain.models import Notification, utc_now
from interactors.api.deps import get_uow
from interactors.api.envelope import ok

router = APIRouter(tags=["notifications"])

_STATUS = {"unread", "read", "resolved"}


def _status_filters(status: str | None) -> dict:
    if status == "unread":
        return {"read_at__isnull": True}
    if status == "read":
        return {"read_at__isnull": False, "resolved_at__isnull": True}
    if status == "resolved":
        return {"resolved_at__isnull": False}
    return {}


@router.get("/notifications")
def list_notifications(
    category: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page_size: int = Query(default=50),
    page_number: int = Query(default=1),
    uow: UnitOfWork = Depends(get_uow),
) -> dict:
    filters: dict = _status_filters(status if status in _STATUS else None)
    if category:
        filters["category"] = category
    with uow.transaction():
        page = uow.notifications.list(filters=filters, page_size=page_size,
                                      page_number=page_number, order_by="-created_at")
    return ok(
        [n.model_dump(mode="json") for n in page.results],
        meta={"total": page.total, "page_size": page.page_size, "page_number": page.page_number},
    )


@router.get("/notifications/unread-count")
def unread_count(uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        page = uow.notifications.list(filters={"read_at__isnull": True}, page_size=1)
    return ok({"count": page.total})


class PatchNotification(BaseModel):
    read: bool | None = None
    resolved: bool | None = None


@router.patch("/notifications/{notification_id}")
def patch_notification(
    notification_id: str, body: PatchNotification, uow: UnitOfWork = Depends(get_uow)
) -> dict:
    with uow.transaction():
        n: Notification = uow.notifications.get(notification_id)  # 404 / owner scope
        updates: dict = {}
        if body.read and n.read_at is None:
            updates["read_at"] = utc_now()
        if body.resolved and n.resolved_at is None:
            updates["resolved_at"] = utc_now()
            if n.read_at is None:
                updates["read_at"] = utc_now()
        result = uow.notifications.update(notification_id, n.model_copy(update=updates))
    return ok(result.model_dump(mode="json"))
