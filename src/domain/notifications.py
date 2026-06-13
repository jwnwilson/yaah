"""Pure policy mapping run events to notifications (no I/O)."""

from domain.models import (
    Notification,
    NotificationAction,
    NotificationCategory,
    NotificationSeverity,
    NotificationSource,
    Run,
    RunEvent,
    RunEventType,
)


def notification_for_event(ev: RunEvent, *, run: Run) -> Notification | None:
    """Map a structural run event to a system notification, or None if it isn't
    user-facing. Pure: never raises on unmapped types."""
    common = dict(
        owner_id=run.owner_id,
        source=NotificationSource.SYSTEM,
        run_id=run.id,
        work_item_id=run.task_id,
    )
    if ev.type == RunEventType.GATE_OPENED:
        return Notification(
            category=NotificationCategory.REVIEW,
            severity=NotificationSeverity.ATTENTION,
            title="Approval needed",
            body=f"A run reached the {ev.stage} gate and needs your approval.",
            action=NotificationAction(kind="gate_approval", run_id=run.id),
            **common,
        )
    if ev.type == RunEventType.BLOCKED:
        return Notification(
            category=NotificationCategory.ALERT,
            severity=NotificationSeverity.ATTENTION,
            title="Run blocked",
            body=ev.message or f"A run blocked at {ev.stage}.",
            **common,
        )
    if ev.type == RunEventType.ERROR:
        return Notification(
            category=NotificationCategory.ALERT,
            severity=NotificationSeverity.CRITICAL,
            title="Run failed",
            body=ev.message or f"A run errored at {ev.stage}.",
            **common,
        )
    return None


def resolves(notification: Notification, ev: RunEvent) -> bool:
    """True when this event resolves the (action-required) notification."""
    return (
        ev.type == RunEventType.GATE_RESOLVED
        and notification.action is not None
        and notification.action.run_id == ev.run_id
    )
