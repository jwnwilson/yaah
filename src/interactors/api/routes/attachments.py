from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import Response

from adapters.database.ports import UnitOfWork
from adapters.storage.ports import StoragePort
from domain.attachments import (
    ALLOWED_ATTACHMENT_TYPES,
    attachment_storage_key,
    canonical_extension,
    is_inline_image,
    sanitize_filename,
)
from domain.errors import RecordNotFound
from domain.models import WorkItemAttachment
from interactors.api.deps import get_uow, storage
from interactors.api.envelope import ok

router = APIRouter(tags=["attachments"])


@router.post("/work-items/{item_id}/attachments")
async def upload(
    item_id: str,
    file: UploadFile,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    store: StoragePort = Depends(storage),
) -> dict:
    max_bytes = request.app.state.settings.max_attachment_bytes
    ext = canonical_extension(file.filename or "")
    if ext is None:
        raise HTTPException(status_code=415, detail="unsupported attachment type")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty file")
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail="attachment too large")

    with uow.transaction():
        item = uow.work_items.get(item_id)  # owner-scoped; RecordNotFound -> 404
        attachment = WorkItemAttachment(
            owner_id=item.owner_id,
            work_item_id=item_id,
            filename=sanitize_filename(file.filename or "file"),
            content_type=ALLOWED_ATTACHMENT_TYPES[ext],
            size_bytes=len(content),
            storage_key="",
        )
        attachment = attachment.model_copy(
            update={"storage_key": attachment_storage_key(item_id, attachment.id, ext)}
        )
        store.write_bytes(attachment.storage_key, content)
        created = uow.work_item_attachments.create(attachment)
    return ok(created.model_dump(mode="json"))


@router.get("/work-items/{item_id}/attachments")
def list_for_item(item_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        page = uow.work_item_attachments.list(
            filters={"work_item_id": item_id}, page_size=200, order_by="created_at"
        )
    return ok([a.model_dump(mode="json") for a in page.results])


@router.get("/attachments/{attachment_id}")
def download(
    attachment_id: str,
    uow: UnitOfWork = Depends(get_uow),
    store: StoragePort = Depends(storage),
) -> Response:
    with uow.transaction():
        att = uow.work_item_attachments.get(attachment_id)  # owner-scoped -> 404
    if not store.exists(att.storage_key):
        raise RecordNotFound("attachment blob missing")
    disposition = "inline" if is_inline_image(att.content_type) else "attachment"
    return Response(
        content=store.read_bytes(att.storage_key),
        media_type=att.content_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{att.filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/attachments/{attachment_id}")
def delete(
    attachment_id: str,
    uow: UnitOfWork = Depends(get_uow),
    store: StoragePort = Depends(storage),
) -> dict:
    with uow.transaction():
        att = uow.work_item_attachments.get(attachment_id)  # owner-scoped -> 404
        store.delete(att.storage_key)
        uow.work_item_attachments.delete(attachment_id)
    return ok({"deleted": attachment_id})
