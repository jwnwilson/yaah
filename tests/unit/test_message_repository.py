from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.models import (
    Message,
    MessageKind,
    MessageRecipientKind,
    MessageSenderKind,
)


def _uow(owner: str = "dev-user") -> SqlUnitOfWork:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return SqlUnitOfWork(make_session_factory(engine), required_filters={"owner_id": owner})


def _msg(**over) -> Message:
    base = dict(
        owner_id="dev-user",
        sender_kind=MessageSenderKind.AGENT,
        sender_agent_id="a-lead",
        recipient_kind=MessageRecipientKind.AGENT,
        recipient_agent_id="a-eng",
        kind=MessageKind.DISPATCH,
        body="go",
        run_id="r1",
    )
    base.update(over)
    return Message(**base)


def test_create_and_get_roundtrips_all_fields():
    uow = _uow()
    with uow.transaction():
        created = uow.messages.create(_msg(subject="brief"))
    with uow.transaction():
        got = uow.messages.get(created.id)
    assert got.subject == "brief"
    assert got.sender_agent_id == "a-lead"
    assert got.recipient_agent_id == "a-eng"
    assert got.kind == MessageKind.DISPATCH


def test_list_filters_by_recipient_mailbox():
    uow = _uow()
    with uow.transaction():
        uow.messages.create(_msg(recipient_agent_id="a-eng"))
        uow.messages.create(_msg(recipient_agent_id="a-qa"))
    with uow.transaction():
        eng = uow.messages.list(filters={"recipient_agent_id": "a-eng"})
    assert eng.total == 1
    assert eng.results[0].recipient_agent_id == "a-eng"


def test_owner_scoping_hides_other_tenants():
    uow = _uow(owner="dev-user")
    with uow.transaction():
        uow.messages.create(_msg(owner_id="dev-user"))
    other = SqlUnitOfWork(
        uow._session_factory, required_filters={"owner_id": "someone-else"}
    )
    with other.transaction():
        assert other.messages.list().total == 0
