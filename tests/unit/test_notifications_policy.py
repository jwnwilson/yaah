from domain.notifications import (
    Notification,
    NotificationAction,
    NotificationCategory,
    NotificationSeverity,
    NotificationSource,
    notification_for_event,
    resolves,
)
from domain.runs import Run, RunEvent, RunEventType, RunStage


def _run():
    return Run(id="r1", owner_id="dev-user", task_id="t1", team_id="tm")


def _event(type_, stage=RunStage.PLAN):
    return RunEvent(run_id="r1", owner_id="dev-user", stage=stage, type=type_)


def test_gate_opened_maps_to_review_action_required():
    n = notification_for_event(_event(RunEventType.GATE_OPENED), run=_run())
    assert n is not None
    assert n.category == NotificationCategory.REVIEW
    assert n.severity == NotificationSeverity.ATTENTION
    assert n.source == NotificationSource.SYSTEM
    assert n.action == NotificationAction(kind="gate_approval", run_id="r1")
    assert n.run_id == "r1" and n.work_item_id == "t1"


def test_blocked_maps_to_attention_alert():
    n = notification_for_event(_event(RunEventType.BLOCKED), run=_run())
    assert n.category == NotificationCategory.ALERT
    assert n.severity == NotificationSeverity.ATTENTION
    assert n.action is None


def test_error_maps_to_critical_alert():
    n = notification_for_event(_event(RunEventType.ERROR), run=_run())
    assert n.category == NotificationCategory.ALERT
    assert n.severity == NotificationSeverity.CRITICAL


def test_unmapped_event_returns_none():
    assert notification_for_event(_event(RunEventType.STAGE_STARTED), run=_run()) is None
    assert notification_for_event(_event(RunEventType.AGENT_EVENT), run=_run()) is None


def test_resolves_matches_gate_resolved_for_same_run():
    n = Notification(owner_id="u", source=NotificationSource.SYSTEM,
                     category=NotificationCategory.REVIEW, title="x", run_id="r1",
                     action=NotificationAction(kind="gate_approval", run_id="r1"))
    assert resolves(n, _event(RunEventType.GATE_RESOLVED)) is True
    assert resolves(n, _event(RunEventType.BLOCKED)) is False
    n_no_action = n.model_copy(update={"action": None})
    assert resolves(n_no_action, _event(RunEventType.GATE_RESOLVED)) is False
