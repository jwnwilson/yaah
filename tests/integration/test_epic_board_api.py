"""Integration tests for the epic-board aggregation endpoint."""
from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def _client():
    return TestClient(create_app(Settings(_env_file=None, database_url="sqlite:///:memory:")))


def _project(c) -> str:
    return c.post("/projects", json={"name": "Alpha", "repo_url": "r"}).json()["data"]["id"]


def _item(c, pid, kind, title, parent_id=None) -> dict:
    return c.post(
        f"/projects/{pid}/work-items",
        json={"kind": kind, "title": title, "parent_id": parent_id},
    ).json()["data"]


def test_epic_board_returns_subtree_with_counts():
    c = _client()
    pid = _project(c)
    epic = _item(c, pid, "epic", "Checkout")
    feature = _item(c, pid, "feature", "Cart", parent_id=epic["id"])
    t1 = _item(c, pid, "task", "t1", parent_id=feature["id"])
    _item(c, pid, "task", "t2", parent_id=feature["id"])

    # move t1 to done so a count is non-zero
    c.post(f"/work-items/{t1['id']}/status", json={"status": "ready"})
    c.post(f"/work-items/{t1['id']}/status", json={"status": "in_progress"})
    c.post(f"/work-items/{t1['id']}/status", json={"status": "in_review"})
    c.post(f"/work-items/{t1['id']}/status", json={"status": "approved"})
    c.post(f"/work-items/{t1['id']}/status", json={"status": "done"})

    r = c.get(f"/projects/{pid}/epics/{epic['id']}/board")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["epic"]["id"] == epic["id"]
    assert data["total"] == 2 and data["done"] == 1
    assert data["features"][0]["feature"]["id"] == feature["id"]
    assert data["features"][0]["total"] == 2 and data["features"][0]["done"] == 1
    assert {t["id"] for t in data["tasks"]} == {t1["id"], data["tasks"][1]["id"]}


def test_empty_epic_returns_zero_counts():
    c = _client()
    pid = _project(c)
    epic = _item(c, pid, "epic", "Lonely")
    data = c.get(f"/projects/{pid}/epics/{epic['id']}/board").json()["data"]
    assert data["features"] == [] and data["total"] == 0 and data["done"] == 0


def test_unknown_epic_returns_404():
    c = _client()
    pid = _project(c)
    r = c.get(f"/projects/{pid}/epics/nope/board")
    assert r.status_code == 404
