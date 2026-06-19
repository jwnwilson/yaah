from domain.messages import (
    Message,
    MessageKind,
    MessageRecipientKind,
    MessageSenderKind,
    MessageSeverity,
    message_for_event,
    message_resolves,
)
from domain.runs import Run, RunEvent, RunEventType, RunStage


def _run():
    return Run(id="r1", owner_id="dev-user", task_id="t1", team_id="tm")


def _event(type_, stage=RunStage.PLAN):
    return RunEvent(run_id="r1", owner_id="dev-user", stage=stage, type=type_)


def test_gate_opened_maps_to_gate_attention_user_message():
    m = message_for_event(_event(RunEventType.GATE_OPENED), run=_run())
    assert m is not None
    assert m.kind == MessageKind.GATE
    assert m.severity == MessageSeverity.ATTENTION
    assert m.sender_kind == MessageSenderKind.SYSTEM
    assert m.recipient_kind == MessageRecipientKind.USER
    assert m.subject == "Approval needed"
    assert m.run_id == "r1" and m.work_item_id == "t1"


def test_blocked_maps_to_notice_attention():
    m = message_for_event(_event(RunEventType.BLOCKED), run=_run())
    assert m.kind == MessageKind.NOTICE
    assert m.severity == MessageSeverity.ATTENTION


def test_error_maps_to_notice_critical():
    m = message_for_event(_event(RunEventType.ERROR), run=_run())
    assert m.kind == MessageKind.NOTICE
    assert m.severity == MessageSeverity.CRITICAL


def test_unmapped_event_returns_none():
    assert message_for_event(_event(RunEventType.STAGE_STARTED), run=_run()) is None
    assert message_for_event(_event(RunEventType.AGENT_EVENT), run=_run()) is None


def test_message_resolves_only_for_gate_resolved_matching_run():
    gate = Message(owner_id="u", sender_kind=MessageSenderKind.SYSTEM,
                   recipient_kind=MessageRecipientKind.USER, kind=MessageKind.GATE,
                   subject="x", run_id="r1")
    assert message_resolves(gate, _event(RunEventType.GATE_RESOLVED)) is True
    assert message_resolves(gate, _event(RunEventType.BLOCKED)) is False
    other_run = gate.model_copy(update={"run_id": "r2"})
    assert message_resolves(other_run, _event(RunEventType.GATE_RESOLVED)) is False
    notice = gate.model_copy(update={"kind": MessageKind.NOTICE})
    assert message_resolves(notice, _event(RunEventType.GATE_RESOLVED)) is False
