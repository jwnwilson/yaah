"""Integration tests for the synchronous refinement chat API (T5)."""
from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def _client():
    return TestClient(create_app(Settings(_env_file=None, database_url="sqlite:///:memory:")))


def _project(c) -> str:
    return c.post("/projects", json={"name": "Alpha", "repo_url": "r"}).json()["data"]["id"]


def test_chat_drafts_a_work_item():
    c = _client()
    pid = _project(c)
    r = c.post(f"/projects/{pid}/chat", json={"message": "build login"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["reply"] and data["session_id"]
    assert len(data["created_items"]) == 1
    item = data["created_items"][0]
    assert item["status"] == "draft" and item["kind"] == "epic"  # never ready
    # the draft is on the board
    items = c.get(f"/projects/{pid}/work-items", params={"kind": "epic"}).json()["data"]
    assert any(i["id"] == item["id"] for i in items)


def test_chat_history_round_trips():
    c = _client()
    pid = _project(c)
    sid = c.post(f"/projects/{pid}/chat", json={"message": "hi"}).json()["data"]["session_id"]
    msgs = c.get(f"/chat/{sid}/messages").json()["data"]
    roles = [m["role"] for m in msgs]
    assert "user" in roles and "assistant" in roles


def test_chat_continues_existing_session():
    c = _client()
    pid = _project(c)
    r1 = c.post(f"/projects/{pid}/chat", json={"message": "first"})
    sid = r1.json()["data"]["session_id"]
    r2 = c.post(f"/projects/{pid}/chat", json={"message": "second", "session_id": sid})
    assert r2.status_code == 200
    assert r2.json()["data"]["session_id"] == sid
    msgs = c.get(f"/chat/{sid}/messages").json()["data"]
    assert len(msgs) == 4  # user + assistant + user + assistant


def test_list_sessions_for_project():
    c = _client()
    pid = _project(c)
    c.post(f"/projects/{pid}/chat", json={"message": "a"})
    c.post(f"/projects/{pid}/chat", json={"message": "b"})
    r = c.get(f"/projects/{pid}/chat")
    assert r.status_code == 200
    sessions = r.json()["data"]
    assert len(sessions) == 2


def test_chat_unknown_project_returns_404():
    c = _client()
    r = c.post("/projects/doesnotexist/chat", json={"message": "hi"})
    assert r.status_code == 404


def test_items_always_created_as_draft():
    """Proposals must land as DRAFT regardless of FakeRefinementAgent output."""
    c = _client()
    pid = _project(c)
    r = c.post(f"/projects/{pid}/chat", json={"message": "anything"})
    for item in r.json()["data"]["created_items"]:
        assert item["status"] == "draft"


def _make_epic(c, pid) -> str:
    return c.post(
        f"/projects/{pid}/work-items", json={"kind": "epic", "title": "Checkout"}
    ).json()["data"]["id"]


def test_epic_scoped_chat_drafts_child_feature_and_returns_proposed_update():
    c = _client()
    pid = _project(c)
    epic_id = _make_epic(c, pid)
    r = c.post(f"/projects/{pid}/chat", json={"message": "cart flow", "epic_id": epic_id})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["proposed_epic_update"] is not None
    assert data["proposed_epic_update"]["body"]
    # the child feature was drafted under the epic
    assert data["created_items"][0]["kind"] == "feature"
    assert data["created_items"][0]["parent_id"] == epic_id


def test_unscoped_chat_has_no_proposed_epic_update():
    c = _client()
    pid = _project(c)
    data = c.post(f"/projects/{pid}/chat", json={"message": "build login"}).json()["data"]
    assert data["proposed_epic_update"] is None
