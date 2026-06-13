from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def _client():
    return TestClient(create_app(Settings(_env_file=None, database_url="sqlite:///:memory:")))


def test_skill_crud_owner_scoped():
    c = _client()
    r = c.post("/skills", json={"name": "pytest", "source": "git@x/s.git"})
    assert r.status_code == 201
    sid = r.json()["data"]["id"]
    assert c.get(f"/skills/{sid}").status_code == 200
    assert c.get("/skills").json()["meta"]["total"] == 1


def test_mcp_and_secret_create():
    c = _client()
    assert c.post("/mcp-servers", json={"name": "fs", "transport": "stdio",
                  "command_or_url": "npx mcp-fs", "tool_allowlist": ["mcp__fs__read"]}).status_code == 201
    assert c.post("/secrets", json={"name": "GH_TOKEN", "description": "gh"}).status_code == 201
