from domain.models import (
    Notification,
    NotificationAction,
    NotificationCategory,
    NotificationSeverity,
    NotificationSource,
)


def test_notification_defaults():
    n = Notification(owner_id="dev-user", source=NotificationSource.SYSTEM,
                     category=NotificationCategory.ALERT, title="run failed")
    assert n.id and len(n.id) == 32
    assert n.severity == NotificationSeverity.INFO
    assert n.read_at is None and n.resolved_at is None
    assert n.action is None


def test_notification_with_gate_action():
    n = Notification(owner_id="u", source=NotificationSource.SYSTEM,
                     category=NotificationCategory.REVIEW, severity=NotificationSeverity.ATTENTION,
                     title="plan ready", run_id="r1",
                     action=NotificationAction(kind="gate_approval", run_id="r1"))
    assert n.action.kind == "gate_approval"
    assert n.action.run_id == "r1"
