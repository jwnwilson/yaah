from domain.models import Notification


class InAppChannel:
    """The inbox itself is the in-app channel; persistence is the delivery, so deliver
    is a no-op."""

    def deliver(self, n: Notification) -> None:
        return None


class FakeChannel:
    """Records delivered notifications (test double for external channels)."""

    def __init__(self) -> None:
        self.delivered: list[Notification] = []

    def deliver(self, n: Notification) -> None:
        self.delivered.append(n)
