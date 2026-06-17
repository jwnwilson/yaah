import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.base import utc_now
from domain.notifications import (
    Notification,
    NotificationAction,
    NotificationCategory,
    NotificationSource,
)


@pytest.fixture
def factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _n(**kw):
    base = dict(owner_id="dev-user", source=NotificationSource.SYSTEM,
                category=NotificationCategory.ALERT, title="t")
    base.update(kw)
    return Notification(**base)


def test_create_list_and_mark_read(factory):
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        created = uow.notifications.create(_n(run_id="r1"))
        uow.notifications.update(created.id, created.model_copy(update={"read_at": utc_now()}))
        fetched = uow.notifications.get(created.id)
    assert fetched.read_at is not None


def test_action_round_trips(factory):
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        created = uow.notifications.create(
            _n(category=NotificationCategory.REVIEW, run_id="r1",
               action=NotificationAction(kind="gate_approval", run_id="r1")))
        fetched = uow.notifications.get(created.id)
    assert fetched.action is not None and fetched.action.run_id == "r1"


def test_owner_scoping(factory):
    a = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with a.transaction():
        a.notifications.create(_n())
    b = SqlUnitOfWork(factory, required_filters={"owner_id": "other"})
    with b.transaction():
        assert b.notifications.list().total == 0
