import logging
from typing import Protocol

from domain.models import Notification

logger = logging.getLogger(__name__)


class NotificationChannel(Protocol):
    def deliver(self, n: Notification) -> None: ...


class NotificationDispatcher:
    """Fans an (already-persisted) notification out to external channels. In-app delivery
    IS persistence, so the in-app channel is a no-op. A channel failure is logged and
    swallowed so it never loses the inbox item or fails a run."""

    def __init__(self, channels: list[NotificationChannel]):
        self._channels = channels

    def deliver(self, n: Notification) -> None:
        for channel in self._channels:
            try:
                channel.deliver(n)
            except Exception:  # noqa: BLE001 - delivery is best-effort
                logger.exception("notification channel %s failed", type(channel).__name__)
