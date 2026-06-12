from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def make_client() -> TestClient:
    app = create_app(Settings(_env_file=None, database_url="sqlite:///:memory:"))
    return TestClient(app)


def test_health():
    resp = make_client().get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"success": True, "data": {"status": "ok"}, "error": None}


def test_unknown_route_envelope():
    resp = make_client().get("/nope")
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["error"]
