from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def _client():
    return TestClient(
        create_app(
            Settings(
                _env_file=None,
                database_url="sqlite:///:memory:",
                secret_key=Fernet.generate_key().decode(),
            )
        )
    )


def test_skill_crud_owner_scoped():
    c = _client()
    r = c.post("/skills", json={"name": "pytest", "source": "git@x/s.git"})
    assert r.status_code == 201
    sid = r.json()["data"]["id"]
    assert c.get(f"/skills/{sid}").status_code == 200
    assert c.get("/skills").json()["meta"]["total"] == 1


def test_mcp_and_secret_create():
    c = _client()
    r = c.post("/mcp-servers", json={
        "name": "fs", "transport": "stdio",
        "command_or_url": "npx mcp-fs", "tool_allowlist": ["mcp__fs__read"],
    })
    assert r.status_code == 201
    assert c.post("/secrets", json={"name": "GH_TOKEN", "description": "gh"}).status_code == 201


def test_secret_value_is_write_only_and_encrypted():
    c = _client()
    sid = c.post("/secrets", json={"name": "GH_TOKEN"}).json()["data"]["id"]
    # read: no value, has_value False
    got = c.get(f"/secrets/{sid}").json()["data"]
    assert "encrypted_value" not in got and got["has_value"] is False
    # set value
    r = c.put(f"/secrets/{sid}/value", json={"value": "ghp_secret"})
    assert r.status_code == 200 and r.json()["data"]["has_value"] is True
    # read again: still no value, has_value True
    got2 = c.get(f"/secrets/{sid}").json()["data"]
    assert "encrypted_value" not in got2 and got2["has_value"] is True
    assert "ghp_secret" not in c.get("/secrets").text  # never serialized in lists either
