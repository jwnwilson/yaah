import pytest

from domain.models import AgentRole, MessageKind, MessageRecipientKind
from domain.orchestration import (
    Dispatch,
    OrchestrationDecision,
    OrchestrationIntent,
    OutboundMessage,
)


def test_continue_decision_with_dispatch_is_valid():
    d = OrchestrationDecision(
        intent=OrchestrationIntent.CONTINUE,
        dispatches=[Dispatch(target_role=AgentRole.BACKEND, instructions="implement X")],
        assignee_role=AgentRole.BACKEND,
    )
    assert d.dispatches[0].acceptance == []
    assert d.rationale == ""


def test_continue_requires_dispatch_or_message():
    with pytest.raises(ValueError, match="continue requires"):
        OrchestrationDecision(intent=OrchestrationIntent.CONTINUE)


def test_block_requires_rationale():
    with pytest.raises(ValueError, match="block requires"):
        OrchestrationDecision(intent=OrchestrationIntent.BLOCK)


def test_verify_and_complete_need_no_dispatches():
    assert OrchestrationDecision(intent=OrchestrationIntent.VERIFY).dispatches == []
    assert OrchestrationDecision(intent=OrchestrationIntent.COMPLETE).intent == (
        OrchestrationIntent.COMPLETE
    )


def test_outbound_agent_message_requires_recipient_role():
    with pytest.raises(ValueError, match="recipient_role"):
        OutboundMessage(recipient_kind=MessageRecipientKind.AGENT, body="hi")


def test_outbound_user_message_is_valid():
    m = OutboundMessage(recipient_kind=MessageRecipientKind.USER, body="status update")
    assert m.kind == MessageKind.CHAT
