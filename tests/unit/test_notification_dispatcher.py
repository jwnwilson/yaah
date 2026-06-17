from adapters.agent.notify.inapp import FakeChannel, InAppChannel
from adapters.agent.notify.ports import NotificationDispatcher
from domain.notifications import Notification, NotificationCategory, NotificationSource


def _n():
    return Notification(owner_id="u", source=NotificationSource.SYSTEM,
                        category=NotificationCategory.ALERT, title="t")


def test_dispatcher_delivers_to_all_channels():
    fake = FakeChannel()
    NotificationDispatcher([InAppChannel(), fake]).deliver(_n())
    assert len(fake.delivered) == 1


def test_dispatcher_swallows_channel_errors():
    class Boom:
        def deliver(self, n):
            raise RuntimeError("smtp down")

    fake = FakeChannel()
    # a throwing channel must not prevent later channels from receiving the notification
    NotificationDispatcher([Boom(), fake]).deliver(_n())
    assert len(fake.delivered) == 1
