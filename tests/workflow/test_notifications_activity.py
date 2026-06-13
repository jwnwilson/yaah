import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from adapters.notify.inapp import FakeChannel
from adapters.notify.ports import NotificationDispatcher
from domain.models import (
    NotificationCategory,
    Project,
    Run,
    RunEventType,
    WorkItem,
    WorkItemKind,
    WorkItemStatus,
)
from interactors.temporal.activities import RunActivities


@pytest.fixture
def factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _seed(factory):
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        uow.projects.create(Project(id="p1", owner_id="dev-user", name="P", local_path="/x"))
        uow.work_items.create(WorkItem(id="t1", owner_id="dev-user", project_id="p1",
                                       kind=WorkItemKind.TASK, parent_id="f1", title="T",
                                       status=WorkItemStatus.IN_PROGRESS))
        uow.runs.create(Run(id="r1", owner_id="dev-user", task_id="t1", team_id="tm"))


def _acts(factory, fake):
    return RunActivities(factory, runtime=None, storage=None, git=None, forge=None,
                         notifier=NotificationDispatcher([fake]))


def test_gate_opened_event_creates_action_required_notification(factory):
    _seed(factory)
    fake = FakeChannel()
    acts = _acts(factory, fake)
    acts.record_event({"run_id": "r1", "owner_id": "dev-user", "stage": "plan",
                       "type": RunEventType.GATE_OPENED, "message": ""})
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        notifs = uow.notifications.list(filters={"run_id": "r1"}).results
    assert len(notifs) == 1
    assert notifs[0].category == NotificationCategory.REVIEW
    assert notifs[0].action is not None
    assert len(fake.delivered) == 1


def test_duplicate_gate_opened_does_not_stack(factory):
    _seed(factory)
    acts = _acts(factory, FakeChannel())
    payload = {"run_id": "r1", "owner_id": "dev-user", "stage": "plan",
               "type": RunEventType.GATE_OPENED, "message": ""}
    acts.record_event(payload)
    acts.record_event(payload)  # resume / retry
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        assert uow.notifications.list(filters={"run_id": "r1"}).total == 1


def test_gate_resolved_auto_resolves_open_notification(factory):
    _seed(factory)
    acts = _acts(factory, FakeChannel())
    acts.record_event({"run_id": "r1", "owner_id": "dev-user", "stage": "plan",
                       "type": RunEventType.GATE_OPENED, "message": ""})
    acts.record_event({"run_id": "r1", "owner_id": "dev-user", "stage": "plan",
                       "type": RunEventType.GATE_RESOLVED, "message": "approved"})
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        notif = uow.notifications.list(filters={"run_id": "r1"}).results[0]
    assert notif.resolved_at is not None


def test_record_notification_persists_agent_flag(factory):
    _seed(factory)
    fake = FakeChannel()
    acts = _acts(factory, fake)
    acts.record_notification({"run_id": "r1", "owner_id": "dev-user",
                              "category": "decision", "title": "DB choice",
                              "body": "Postgres over SQLite", "severity": "info"})
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        notif = uow.notifications.list(filters={"run_id": "r1"}).results[0]
    assert notif.source.value == "agent"
    assert notif.category == NotificationCategory.DECISION
    assert notif.work_item_id == "t1"
    assert len(fake.delivered) == 1
