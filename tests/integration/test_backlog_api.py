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

    resp = c.post(f"/projects/{pid}/epics/{epic_id}/activate")
    assert resp.status_code == 200
    assert resp.json()["data"]["active"] is True
    assert len(fake.started) == 2


def test_deactivate_epic_starts_nothing():
    c, fake = _client()
    pid = _project_with_team(c)
    epic_id = _epic_with_ready_tasks(c, pid, 1)
    c.post(f"/projects/{pid}/epics/{epic_id}/activate")
    fake.started.clear()
    resp = c.post(f"/projects/{pid}/epics/{epic_id}/deactivate")
    assert resp.status_code == 200
    assert resp.json()["data"]["active"] is False
    assert fake.started == []


def test_activate_non_epic_404():
    c, _fake = _client()
    pid = _project_with_team(c)
    epic = c.post(f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E"}).json()["data"]
    feat = c.post(f"/projects/{pid}/work-items",
                  json={"kind": "feature", "title": "F", "parent_id": epic["id"]}).json()["data"]
    assert c.post(f"/projects/{pid}/epics/{feat['id']}/activate").status_code == 404


def test_ready_task_under_active_epic_autostarts():
    c, fake = _client()
    pid = _project_with_team(c)
    epic = c.post(f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E"}).json()["data"]
    c.post(f"/projects/{pid}/epics/{epic['id']}/activate")
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
    c.post(f"/projects/{pid}/epics/{epic_id}/activate")
    assert len(fake.started) == 1
    c.patch(f"/projects/{pid}", json={"max_concurrent_runs": 3})
    assert len(fake.started) == 3
