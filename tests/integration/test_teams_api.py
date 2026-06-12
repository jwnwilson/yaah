from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def make_client() -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, database_url="sqlite:///:memory:")))


def test_create_default_team_and_fetch_agents():
    c = make_client()
    created = c.post("/teams/default")
    assert created.status_code == 201
    team = created.json()["data"]["team"]
    agents = created.json()["data"]["agents"]
    assert [a["role"] for a in agents] == ["lead", "backend", "qa"]

    assert c.get("/teams").json()["data"][0]["id"] == team["id"]
    fetched = c.get(f"/teams/{team['id']}").json()["data"]
    assert fetched["team"]["id"] == team["id"]
    assert [a["role"] for a in fetched["agents"]] == ["lead", "backend", "qa"]


def test_get_missing_team_404():
    assert make_client().get("/teams/nope").status_code == 404
