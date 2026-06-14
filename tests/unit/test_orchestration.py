import pytest

from domain.models import (
    AgentRole,
    MessageKind,
    MessageRecipientKind,
    MessageSenderKind,
)
from domain.orchestration import (
    AgentOutcome,
    AgentReport,
    AgentStepResult,
    Dispatch,
    MonitorVerdict,
    OrchestrationDecision,
    OrchestrationIntent,
    OrchestrationLimits,
    OrchestrationState,
    OutboundMessage,
    decision_to_messages,
    guard_exceeded,
    is_quiescent,
    resolve_assignee,
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


def test_agent_step_result_defaults():
    r = AgentStepResult()
    assert r.outcome == AgentOutcome.OK
    assert r.completed_brief is False
    assert r.outgoing == [] and r.artifacts == {} and r.cost_usd == 0.0


def test_agent_report_carries_outcome_and_cost():
    rep = AgentReport(
        role=AgentRole.QA, outcome=AgentOutcome.FAIL, summary="2 failing", cost_usd=0.5
    )
    assert rep.outcome == AgentOutcome.FAIL and rep.cost_usd == 0.5


def test_monitor_verdict_complete_and_incomplete():
    ok = MonitorVerdict(complete=True)
    assert ok.unmet == [] and ok.pending_mailboxes == []
    bad = MonitorVerdict(complete=False, unmet=["no tests"], pending_mailboxes=["qa"])
    assert bad.unmet == ["no tests"]


def test_state_records_wave_report_and_cost_immutably():
    s0 = OrchestrationState()
    s1 = s0.record_wave(dispatch_count=2, messages=2, cost=1.5)
    s2 = s1.record_report(AgentReport(role=AgentRole.BACKEND, outcome=AgentOutcome.OK))
    assert s0.waves == 0 and s0.total_dispatches == 0          # original untouched
    assert s1.waves == 1 and s1.total_dispatches == 2 and s1.total_cost_usd == 1.5
    assert s2.reports[0].role == AgentRole.BACKEND


def test_guard_exceeded_flags_each_limit():
    limits = OrchestrationLimits(max_waves=2, max_dispatches=3, max_messages=5, max_cost_usd=10.0)
    below = OrchestrationState(
        waves=1, total_dispatches=2, messages_sent=4, total_cost_usd=9.0
    )
    assert guard_exceeded(below, limits) is None
    # Hard caps: a state AT the limit blocks (>=).
    assert guard_exceeded(OrchestrationState(waves=2), limits) == "max_waves"
    assert guard_exceeded(OrchestrationState(total_dispatches=3), limits) == "max_dispatches"
    assert guard_exceeded(OrchestrationState(messages_sent=5), limits) == "max_messages"
    assert guard_exceeded(OrchestrationState(total_cost_usd=10.0), limits) == "max_cost_usd"


def test_is_quiescent_only_when_idle_and_no_inflight():
    assert is_quiescent(active_agents=0, in_flight_messages=0) is True
    assert is_quiescent(active_agents=1, in_flight_messages=0) is False
    assert is_quiescent(active_agents=0, in_flight_messages=2) is False


def _role_map():
    return {AgentRole.LEAD: "a-lead", AgentRole.BACKEND: "a-eng", AgentRole.QA: "a-qa"}


def test_decision_to_messages_builds_dispatch_and_user_note():
    decision = OrchestrationDecision(
        intent=OrchestrationIntent.CONTINUE,
        dispatches=[Dispatch(target_role=AgentRole.BACKEND, instructions="build it")],
        messages=[OutboundMessage(recipient_kind=MessageRecipientKind.USER, body="starting")],
    )
    msgs = decision_to_messages(
        decision,
        owner_id="dev-user",
        lead_agent_id="a-lead",
        run_id="r1",
        work_item_id="w1",
        project_id="p1",
        role_to_agent_id=_role_map(),
    )
    assert len(msgs) == 2
    dispatch = next(m for m in msgs if m.kind == MessageKind.DISPATCH)
    assert dispatch.sender_kind == MessageSenderKind.AGENT and dispatch.sender_agent_id == "a-lead"
    assert dispatch.recipient_kind == MessageRecipientKind.AGENT
    assert dispatch.recipient_agent_id == "a-eng"
    assert dispatch.body == "build it" and dispatch.run_id == "r1"
    note = next(m for m in msgs if m.recipient_kind == MessageRecipientKind.USER)
    assert note.recipient_agent_id is None and note.body == "starting"


def test_decision_to_messages_skips_unknown_role():
    decision = OrchestrationDecision(
        intent=OrchestrationIntent.CONTINUE,
        dispatches=[Dispatch(target_role=AgentRole.DEVOPS, instructions="x")],
    )
    msgs = decision_to_messages(
        decision, owner_id="o", lead_agent_id="a-lead", run_id="r1",
        work_item_id=None, project_id=None, role_to_agent_id=_role_map(),
    )
    assert msgs == []  # DEVOPS not on the team -> nothing to deliver


def test_resolve_assignee_maps_role_to_agent():
    d = OrchestrationDecision(intent=OrchestrationIntent.VERIFY, assignee_role=AgentRole.BACKEND)
    assert resolve_assignee(d, _role_map()) == "a-eng"
    assert resolve_assignee(
        OrchestrationDecision(intent=OrchestrationIntent.VERIFY), _role_map()
    ) is None


def test_resolve_assignee_returns_none_for_absent_role():
    d = OrchestrationDecision(intent=OrchestrationIntent.VERIFY, assignee_role=AgentRole.DEVOPS)
    assert resolve_assignee(d, _role_map()) is None  # DEVOPS not on the team


def test_record_verdict_is_immutable():
    s0 = OrchestrationState()
    s1 = s0.record_verdict(MonitorVerdict(complete=False, unmet=["no tests"]))
    assert s0.verdicts == []  # original untouched
    assert len(s1.verdicts) == 1 and s1.verdicts[0].unmet == ["no tests"]


def test_needs_human_with_rationale_is_valid():
    d = OrchestrationDecision(
        intent=OrchestrationIntent.NEEDS_HUMAN, rationale="approval needed"
    )
    assert d.intent == OrchestrationIntent.NEEDS_HUMAN


def test_needs_human_requires_rationale_or_user_message():
    with pytest.raises(ValueError, match="needs_human requires"):
        OrchestrationDecision(intent=OrchestrationIntent.NEEDS_HUMAN)
