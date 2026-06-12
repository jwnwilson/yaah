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


def test_record_not_found_maps_to_404_envelope():
    app = create_app(Settings(_env_file=None, database_url="sqlite:///:memory:"))

    from domain.errors import RecordNotFound

    @app.get("/_boom")
    def boom() -> dict:
        raise RecordNotFound("Project x not found")

    resp = TestClient(app, raise_server_exceptions=False).get("/_boom")
    assert resp.status_code == 404
    assert resp.json() == {"success": False, "data": None, "error": "Project x not found"}


def test_integrity_conflict_maps_to_409():
    app = create_app(Settings(_env_file=None, database_url="sqlite:///:memory:"))

    from domain.errors import IntegrityConflict

    @app.get("/_conflict")
    def conflict() -> dict:
        raise IntegrityConflict("duplicate")

    resp = TestClient(app, raise_server_exceptions=False).get("/_conflict")
    assert resp.status_code == 409
