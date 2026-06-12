from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def make_client() -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, database_url="sqlite:///:memory:")))


def _project(c: TestClient) -> str:
    return c.post("/projects", json={"name": "p", "repo_url": "r"}).json()["data"]["id"]


def test_epic_feature_task_hierarchy_and_filters():
    c = make_client()
    pid = _project(c)
    epic = c.post(f"/projects/{pid}/work-items", json={"kind": "epic", "title": "Harness"}).json()[
        "data"
    ]
    feature = c.post(
        f"/projects/{pid}/work-items",
        json={"kind": "feature", "title": "Board", "parent_id": epic["id"]},
    ).json()["data"]
    task = c.post(
        f"/projects/{pid}/work-items",
        json={
            "kind": "task",
            "title": "Kanban columns",
            "parent_id": feature["id"],
            "acceptance_criteria": ["columns render", "drag updates status"],
        },
    ).json()["data"]
    assert task["status"] == "draft"

    tasks = c.get(f"/projects/{pid}/work-items", params={"kind": "task"}).json()["data"]
    assert [t["id"] for t in tasks] == [task["id"]]
    children = c.get(f"/projects/{pid}/work-items", params={"parent_id": feature["id"]}).json()[
        "data"
    ]
    assert [t["id"] for t in children] == [task["id"]]


def test_task_without_parent_rejected():
    c = make_client()
    pid = _project(c)
    resp = c.post(f"/projects/{pid}/work-items", json={"kind": "task", "title": "orphan"})
    assert resp.status_code == 422


def test_status_transition_enforced():
    c = make_client()
    pid = _project(c)
    epic = c.post(f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E"}).json()["data"]
    ok_resp = c.post(f"/work-items/{epic['id']}/status", json={"status": "ready"})
    assert ok_resp.json()["data"]["status"] == "ready"
    bad = c.post(f"/work-items/{epic['id']}/status", json={"status": "done"})
    assert bad.status_code == 409


def test_update_and_delete_work_item():
    c = make_client()
    pid = _project(c)
    epic = c.post(f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E"}).json()["data"]
    patched = c.patch(f"/work-items/{epic['id']}", json={"title": "E2", "body": "details"})
    assert patched.json()["data"]["title"] == "E2"
    assert c.delete(f"/work-items/{epic['id']}").status_code == 200
    assert c.patch(f"/work-items/{epic['id']}", json={"title": "x"}).status_code == 404
