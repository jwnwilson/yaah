"""Repository + owner-scoping for work-item attachments (SQLite in-memory)."""
import pytest

from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.errors import RecordNotFound
from domain.models import WorkItemAttachment


def _uow(owner: str) -> SqlUnitOfWork:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return SqlUnitOfWork(make_session_factory(engine), required_filters={"owner_id": owner})


def test_create_list_get_delete_owner_scoped():
    uow = _uow("alice")
    with uow.transaction():
        a = uow.work_item_attachments.create(
            WorkItemAttachment(
                owner_id="alice", work_item_id="wi1", filename="a.png",
                content_type="image/png", size_bytes=4, storage_key="attachments/wi1/a.png",
            )
        )
    with uow.transaction():
        listed = uow.work_item_attachments.list(filters={"work_item_id": "wi1"}).results
        assert [x.id for x in listed] == [a.id]
        got = uow.work_item_attachments.get(a.id)
        assert got.filename == "a.png"
    with uow.transaction():
        uow.work_item_attachments.delete(a.id)
    with uow.transaction(), pytest.raises(RecordNotFound):
        uow.work_item_attachments.get(a.id)
