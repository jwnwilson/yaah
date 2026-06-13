from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def _client():
    return TestClient(create_app(Settings(_env_file=None, database_url="sqlite:///:memory:")))


def _team(c) -> str:
    return c.post("/teams/default").json()["data"]["team"]["id"]


def test_create_agent_with_valid_grants():
    c = _client()
    tid = _team(c)
    sid = c.post("/skills", json={"name": "pytest"}).json()["data"]["id"]
    r = c.post(f"/teams/{tid}/agents", json={
        "role": "backend", "name": "Eng", "model_alias": "m",
        "purpose": "build", "system_prompt": "you build",
        "allowed_tools": ["Read", "Edit"], "skill_ids": [sid]})
    assert r.status_code == 201
    aid = r.json()["data"]["id"]
    assert c.get(f"/agents/{aid}").json()["data"]["skill_ids"] == [sid]


def test_create_agent_with_bogus_grant_is_404():
    c = _client()
    tid = _team(c)
    r = c.post(f"/teams/{tid}/agents", json={"role": "qa", "name": "Q", "model_alias": "m",
               "skill_ids": ["nope"]})
    assert r.status_code == 404


def test_agents_listed_under_team_and_patch():
    c = _client()
    tid = _team(c)
    aid = c.post(f"/teams/{tid}/agents", json={"role": "lead", "name": "L",
                 "model_alias": "m"}).json()["data"]["id"]
    assert c.get(f"/teams/{tid}/agents").json()["meta"]["total"] >= 1
    patched = c.patch(f"/agents/{aid}", json={"purpose": "lead it"})
    assert patched.json()["data"]["purpose"] == "lead it"
