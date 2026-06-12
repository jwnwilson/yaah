from fastapi.testclient import TestClient

from interactors.api.app import create_app


def test_api_routes_still_envelope_when_ui_absent():
    # The static mount must not shadow /health or /api-style routes.
    app = create_app()
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
