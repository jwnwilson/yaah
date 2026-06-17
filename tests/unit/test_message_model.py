import pytest

from domain.messages import Message, MessageKind, MessageRecipientKind, MessageSenderKind
from domain.projects import WorkItem, WorkItemKind


def test_agent_to_agent_message_is_valid():
    msg = Message(
        owner_id="dev-user",
        sender_kind=MessageSenderKind.AGENT,
        sender_agent_id="a-lead",
        recipient_kind=MessageRecipientKind.AGENT,
        recipient_agent_id="a-eng",
        kind=MessageKind.DISPATCH,
        body="implement the thing",
    )
    assert msg.id and len(msg.id) == 32
    assert msg.delivered_at is None and msg.processed_at is None and msg.read_at is None


def test_agent_sender_requires_sender_agent_id():
    with pytest.raises(ValueError, match="sender_agent_id"):
        Message(
            owner_id="dev-user",
            sender_kind=MessageSenderKind.AGENT,
            recipient_kind=MessageRecipientKind.USER,
            body="hi",
        )


def test_agent_recipient_requires_recipient_agent_id():
    with pytest.raises(ValueError, match="recipient_agent_id"):
        Message(
            owner_id="dev-user",
            sender_kind=MessageSenderKind.SYSTEM,
            recipient_kind=MessageRecipientKind.AGENT,
            body="hi",
        )


def test_system_to_user_message_needs_no_agent_ids():
    msg = Message(
        owner_id="dev-user",
        sender_kind=MessageSenderKind.SYSTEM,
        recipient_kind=MessageRecipientKind.USER,
        body="done",
    )
    assert msg.kind == MessageKind.CHAT  # default


def test_non_agent_sender_must_not_carry_sender_agent_id():
    with pytest.raises(ValueError, match="non-agent sender must not carry sender_agent_id"):
        Message(
            owner_id="dev-user",
            sender_kind=MessageSenderKind.SYSTEM,
            sender_agent_id="a-lead",
            recipient_kind=MessageRecipientKind.USER,
            body="hi",
        )


def test_non_agent_recipient_must_not_carry_recipient_agent_id():
    with pytest.raises(
        ValueError, match="non-agent recipient must not carry recipient_agent_id"
    ):
        Message(
            owner_id="dev-user",
            sender_kind=MessageSenderKind.SYSTEM,
            recipient_kind=MessageRecipientKind.USER,
            recipient_agent_id="a-eng",
            body="hi",
        )


def test_work_item_assignee_defaults_to_none():
    item = WorkItem(
        owner_id="dev-user",
        project_id="p1",
        kind=WorkItemKind.EPIC,
        title="epic",
    )
    assert item.assignee_agent_id is None


def test_work_item_accepts_assignee():
    item = WorkItem(
        owner_id="dev-user",
        project_id="p1",
        kind=WorkItemKind.EPIC,
        title="epic",
        assignee_agent_id="a-eng",
    )
    assert item.assignee_agent_id == "a-eng"
