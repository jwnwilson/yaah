from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.deps import temporal_client
from interactors.api.settings import Settings


class _FakeTemporal:
    def __init__(self):
        self.started = []

    def start_run_workflow(self, run_input, workflow_name="OrchestratorWorkflow"):
        self.started.append((workflow_name, run_input))

    def signal(self, run_id, name):  # pragma: no cover - unused here
        pass


def _client():
    app = create_app(Settings(_env_file=None, database_url="sqlite:///:memory:"))
    fake = _FakeTemporal()
    app.dependency_overrides[temporal_client] = lambda: fake
    return TestClient(app), fake


def _project_with_team(c) -> str:
    pid = c.post("/projects", json={"name": "p", "repo_url": "r"}).json()["data"]["id"]
    team_id = c.post("/teams/default").json()["data"]["team"]["id"]
    c.patch(f"/projects/{pid}", json={"team_id": team_id})
    return pid


def _epic_with_ready_tasks(c, pid, n) -> str:
    epic = c.post(f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E"}).json()["data"]
    for i in range(n):
        t = c.post(f"/projects/{pid}/work-items",
                   json={"kind": "task", "title": f"T{i}", "parent_id": epic["id"]}).json()["data"]
        c.post(f"/work-items/{t['id']}/status", json={"status": "ready"})
    return epic["id"]


def test_activate_epic_starts_runs_up_to_limit():
    c, fake = _client()
    pid = _project_with_team(c)
    c.patch(f"/projects/{pid}", json={"max_concurrent_runs": 2})
    epic_id = _epic_with_ready_tasks(c, pid, 3)

    resp = c.post(f"/projects/{pid}/work-items/{epic_id}/activate")
    assert resp.status_code == 200
    assert resp.json()["data"]["active"] is True
    assert len(fake.started) == 2


def test_deactivate_epic_starts_nothing():
    c, fake = _client()
    pid = _project_with_team(c)
    epic_id = _epic_with_ready_tasks(c, pid, 1)
    c.post(f"/projects/{pid}/work-items/{epic_id}/activate")
    fake.started.clear()
    resp = c.post(f"/projects/{pid}/work-items/{epic_id}/deactivate")
    assert resp.status_code == 200
    assert resp.json()["data"]["active"] is False
    assert fake.started == []


def test_activate_task_404():
    c, _fake = _client()
    pid = _project_with_team(c)
    epic = c.post(f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E"}).json()["data"]
    feat = c.post(f"/projects/{pid}/work-items",
                  json={"kind": "feature", "title": "F", "parent_id": epic["id"]}).json()["data"]
    task = c.post(f"/projects/{pid}/work-items",
                  json={"kind": "task", "title": "T", "parent_id": feat["id"]}).json()["data"]
    # tasks can't be activated; epics and features can
    assert c.post(f"/projects/{pid}/work-items/{task['id']}/activate").status_code == 404


def test_activate_feature_autostarts_its_ready_tasks():
    c, fake = _client()
    pid = _project_with_team(c)
    epic = c.post(f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E"}).json()["data"]
    feat = c.post(f"/projects/{pid}/work-items",
                  json={"kind": "feature", "title": "F", "parent_id": epic["id"]}).json()["data"]
    task = c.post(f"/projects/{pid}/work-items",
                  json={"kind": "task", "title": "T", "parent_id": feat["id"]}).json()["data"]
    c.post(f"/work-items/{task['id']}/status", json={"status": "ready"})
    # epic is NOT active; activating the feature alone should start its ready task
    resp = c.post(f"/projects/{pid}/work-items/{feat['id']}/activate")
    assert resp.status_code == 200
    assert resp.json()["data"]["active"] is True
    assert len(fake.started) == 1
    assert fake.started[0][1]["task_id"] == task["id"]


def test_ready_task_under_active_epic_autostarts():
    c, fake = _client()
    pid = _project_with_team(c)
    epic = c.post(f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E"}).json()["data"]
    c.post(f"/projects/{pid}/work-items/{epic['id']}/activate")
    assert fake.started == []
    task = c.post(f"/projects/{pid}/work-items",
                  json={"kind": "task", "title": "T", "parent_id": epic["id"]}).json()["data"]
    c.post(f"/work-items/{task['id']}/status", json={"status": "ready"})
    assert len(fake.started) == 1
    assert fake.started[0][1]["task_id"] == task["id"]


def test_ready_task_under_inactive_epic_does_not_start():
    c, fake = _client()
    pid = _project_with_team(c)
    epic = c.post(f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E"}).json()["data"]
    task = c.post(f"/projects/{pid}/work-items",
                  json={"kind": "task", "title": "T", "parent_id": epic["id"]}).json()["data"]
    c.post(f"/work-items/{task['id']}/status", json={"status": "ready"})
    assert fake.started == []


def test_raising_cap_pulls_more_work():
    c, fake = _client()
    pid = _project_with_team(c)
    c.patch(f"/projects/{pid}", json={"max_concurrent_runs": 1})
    epic_id = _epic_with_ready_tasks(c, pid, 3)
    c.post(f"/projects/{pid}/work-items/{epic_id}/activate")
    assert len(fake.started) == 1
    c.patch(f"/projects/{pid}", json={"max_concurrent_runs": 3})
    assert len(fake.started) == 3


def test_backlog_endpoint_reports_readiness_and_summary():
    c, _fake = _client()
    pid = _project_with_team(c)
    c.patch(f"/projects/{pid}", json={"max_concurrent_runs": 2})
    epic_id = _epic_with_ready_tasks(c, pid, 2)

    body = c.get(f"/projects/{pid}/backlog").json()
    assert body["success"] is True
    data = body["data"]
    assert data["max_concurrent_runs"] == 2
    assert data["queued"] == 0
    epic = next(e for e in data["epics"] if e["epic"]["id"] == epic_id)
    assert epic["ready_count"] == 2
    assert epic["total_tasks"] == 2
    assert epic["active"] is False


def test_backlog_returns_nested_tree():
    c, _fake = _client()
    pid = _project_with_team(c)
    epic = c.post(f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E"}).json()["data"]
    feat = c.post(f"/projects/{pid}/work-items",
                  json={"kind": "feature", "title": "F", "parent_id": epic["id"]}).json()["data"]
    c.post(f"/projects/{pid}/work-items",
           json={"kind": "task", "title": "T", "parent_id": feat["id"]})
    data = c.get(f"/projects/{pid}/backlog").json()["data"]
    e = next(x for x in data["epics"] if x["epic"]["id"] == epic["id"])
    assert e["features"][0]["feature"]["id"] == feat["id"]
    assert e["features"][0]["tasks"][0]["title"] == "T"


def test_create_appends_position_and_reorder_swaps():
    c, _fake = _client()
    pid = _project_with_team(c)
    e1 = c.post(f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E1"}).json()["data"]
    e2 = c.post(f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E2"}).json()["data"]
    assert e1["position"] == 0 and e2["position"] == 1
    r = c.post(f"/projects/{pid}/work-items/reorder",
               json={"parent_id": None, "ordered_ids": [e2["id"], e1["id"]]})
    assert r.status_code == 200
    data = c.get(f"/projects/{pid}/backlog").json()["data"]
    assert [x["epic"]["id"] for x in data["epics"]] == [e2["id"], e1["id"]]


def test_reorder_rejects_non_sibling():
    c, _fake = _client()
    pid = _project_with_team(c)
    epic = c.post(f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E"}).json()["data"]
    # epic has parent None; asking to reorder it under a feature parent is invalid
    r = c.post(f"/projects/{pid}/work-items/reorder",
               json={"parent_id": "someparent", "ordered_ids": [epic["id"]]})
    assert r.status_code == 400


def test_cascade_delete_removes_descendants():
    c, _fake = _client()
    pid = _project_with_team(c)
    epic = c.post(f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E"}).json()["data"]
    feat = c.post(f"/projects/{pid}/work-items",
                  json={"kind": "feature", "title": "F", "parent_id": epic["id"]}).json()["data"]
    c.post(f"/projects/{pid}/work-items",
           json={"kind": "task", "title": "T1", "parent_id": feat["id"]})
    c.post(f"/projects/{pid}/work-items",
           json={"kind": "task", "title": "T2", "parent_id": feat["id"]})
    resp = c.delete(f"/work-items/{epic['id']}")
    assert resp.status_code == 200
    assert resp.json()["data"]["removed"] == 4  # epic + feature + 2 tasks
    remaining = c.get(f"/projects/{pid}/work-items").json()["data"]
    assert remaining == []


def test_position_orders_autostart_queue():
    c, fake = _client()
    pid = _project_with_team(c)
    c.patch(f"/projects/{pid}", json={"max_concurrent_runs": 1})
    epic = c.post(f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E"}).json()["data"]
    a = c.post(f"/projects/{pid}/work-items",
               json={"kind": "task", "title": "A", "parent_id": epic["id"]}).json()["data"]
    b = c.post(f"/projects/{pid}/work-items",
               json={"kind": "task", "title": "B", "parent_id": epic["id"]}).json()["data"]
    # put B before A, then mark both ready, then activate -> only 1 slot -> B starts first
    c.post(f"/projects/{pid}/work-items/reorder",
           json={"parent_id": epic["id"], "ordered_ids": [b["id"], a["id"]]})
    c.post(f"/work-items/{a['id']}/status", json={"status": "ready"})
    c.post(f"/work-items/{b['id']}/status", json={"status": "ready"})
    c.post(f"/projects/{pid}/work-items/{epic['id']}/activate")
    assert len(fake.started) == 1
    assert fake.started[0][1]["task_id"] == b["id"]


def test_activate_epic_cascades_active_to_features():
    c, _fake = _client()
    pid = _project_with_team(c)
    epic = c.post(f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E"}).json()["data"]
    f1 = c.post(f"/projects/{pid}/work-items",
                json={"kind": "feature", "title": "F1", "parent_id": epic["id"]}).json()["data"]
    f2 = c.post(f"/projects/{pid}/work-items",
                json={"kind": "feature", "title": "F2", "parent_id": epic["id"]}).json()["data"]

    c.post(f"/projects/{pid}/work-items/{epic['id']}/activate")
    data = c.get(f"/projects/{pid}/backlog").json()["data"]
    be = next(e for e in data["epics"] if e["epic"]["id"] == epic["id"])
    assert be["active"] is True
    assert all(bf["feature"]["active"] is True for bf in be["features"])

    # deactivating the epic cascades off
    c.post(f"/projects/{pid}/work-items/{epic['id']}/deactivate")
    data = c.get(f"/projects/{pid}/backlog").json()["data"]
    be = next(e for e in data["epics"] if e["epic"]["id"] == epic["id"])
    assert be["active"] is False
    assert all(bf["feature"]["active"] is False for bf in be["features"])
    assert {f1["id"], f2["id"]} == {bf["feature"]["id"] for bf in be["features"]}
