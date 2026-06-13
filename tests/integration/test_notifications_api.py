from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def _client():
    return TestClient(create_app(Settings(_env_file=None, database_url="sqlite:///:memory:",
                                          auth_mode="dev")))


def _seed(client, **over):
    from adapters.database.uow import SqlUnitOfWork
    from domain.models import Notification, NotificationCategory, NotificationSource
    uow = SqlUnitOfWork(client.app.state.session_factory,
                        required_filters={"owner_id": "dev-user"})
    payload = dict(owner_id="dev-user", source=NotificationSource.SYSTEM,
                   category=NotificationCategory.ALERT, title="run failed", run_id="r1")
    payload.update(over)
    with uow.transaction():
        return uow.notifications.create(Notification(**payload)).id


def test_list_and_unread_count():
    client = _client()
    _seed(client)
    _seed(client, category="update", title="progress")
    assert len(client.get("/notifications").json()["data"]) == 2
    assert client.get("/notifications/unread-count").json()["data"]["count"] == 2


def test_filter_by_category():
    client = _client()
    _seed(client)
    _seed(client, category="update", title="progress")
    only_alert = client.get("/notifications", params={"category": "alert"}).json()["data"]
    assert len(only_alert) == 1 and only_alert[0]["category"] == "alert"


def test_mark_read_then_resolve_updates_unread_count():
    client = _client()
    nid = _seed(client)
    assert client.patch(f"/notifications/{nid}", json={"read": True}).status_code == 200
    assert client.get("/notifications/unread-count").json()["data"]["count"] == 0
    resolved = client.patch(f"/notifications/{nid}", json={"resolved": True}).json()["data"]
    assert resolved["resolved_at"] is not None
    assert len(client.get("/notifications", params={"status": "resolved"}).json()["data"]) == 1


def test_patch_unknown_id_is_404():
    client = _client()
    assert client.patch("/notifications/nope", json={"read": True}).status_code == 404
