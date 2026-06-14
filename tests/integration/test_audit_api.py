# tests/integration/test_audit_api.py
from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def _client():
    return TestClient(
        create_app(Settings(_env_file=None, database_url="sqlite:///:memory:", auth_mode="dev"))
    )


def _seed(client):
    app = client.app
    from adapters.database.uow import SqlUnitOfWork
    from domain.models import AuditAction, AuditEvent
    uow = SqlUnitOfWork(app.state.session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        uow.audit_events.create(AuditEvent(owner_id="dev-user", run_id="r1", actor="lead",
                                           action=AuditAction.TOOL_ALLOWED, detail={"tool": "Read"}))
        uow.audit_events.create(AuditEvent(owner_id="dev-user", run_id="r1", actor="lead",
                                           action=AuditAction.TOOL_DENIED, detail={"tool": "Bash"}))
        uow.audit_events.create(AuditEvent(owner_id="dev-user", run_id="r2", actor="eng",
                                           action=AuditAction.CAPABILITY_GRANTED, detail={}))


def test_audit_lists_all_owner_events_newest_first():
    client = _client()
    _seed(client)
    body = client.get("/audit").json()
    assert body["success"] is True
    assert body["meta"]["total"] == 3
    assert len(body["data"]) == 3


def test_audit_filters_by_run():
    client = _client()
    _seed(client)
    data = client.get("/audit", params={"run_id": "r2"}).json()["data"]
    assert len(data) == 1
    assert data[0]["action"] == "capability_granted"


def test_audit_filters_by_action():
    client = _client()
    _seed(client)
    data = client.get("/audit", params={"action": "tool_denied"}).json()["data"]
    assert len(data) == 1
    assert data[0]["detail"]["tool"] == "Bash"


def test_audit_rejects_bad_action():
    client = _client()
    assert client.get("/audit", params={"action": "nope"}).status_code == 422


def test_audit_paginates():
    client = _client()
    _seed(client)
    body = client.get("/audit", params={"page_size": 2, "page_number": 1}).json()
    assert len(body["data"]) == 2
    assert body["meta"]["total"] == 3


def test_audit_empty():
    client = _client()
    body = client.get("/audit").json()
    assert body["data"] == []
    assert body["meta"]["total"] == 0
