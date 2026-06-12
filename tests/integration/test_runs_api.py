from fastapi.testclient import TestClient

from adapters.database.uow import SqlUnitOfWork
from domain.models import Run, RunStatus
from interactors.api.app import create_app
from interactors.api.settings import Settings


def make_client() -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, database_url="sqlite:///:memory:")))


def _ready_task(c: TestClient) -> tuple[str, str, str]:
    pid = c.post("/projects", json={"name": "p", "repo_url": "r"}).json()["data"]["id"]
    team_id = c.post("/teams/default").json()["data"]["team"]["id"]
    c.patch(f"/projects/{pid}", json={"team_id": team_id})
    epic = c.post(f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E"}).json()["data"]
    feat = c.post(
        f"/projects/{pid}/work-items",
        json={"kind": "feature", "title": "F", "parent_id": epic["id"]},
    ).json()["data"]
    task = c.post(
        f"/projects/{pid}/work-items",
        json={"kind": "task", "title": "T", "parent_id": feat["id"]},
    ).json()["data"]
    c.post(f"/work-items/{task['id']}/status", json={"status": "ready"})
    return task["id"], team_id, pid


def test_start_run_on_ready_task():
    c = make_client()
    task_id, team_id, pid = _ready_task(c)
    resp = c.post(f"/work-items/{task_id}/runs")
    assert resp.status_code == 201
    run = resp.json()["data"]
    assert run["status"] == "pending"
    assert run["team_id"] == team_id
    items = c.get(f"/projects/{pid}/work-items", params={"kind": "task"}).json()["data"]
    assert items[0]["status"] == "in_progress"
    runs = c.get(f"/work-items/{task_id}/runs").json()["data"]
    assert [r["id"] for r in runs] == [run["id"]]
    assert c.get(f"/runs/{run['id']}").json()["data"]["id"] == run["id"]


def test_run_rejected_unless_task_ready():
    c = make_client()
    task_id, _, _ = _ready_task(c)
    c.post(f"/work-items/{task_id}/runs")  # consumes ready -> in_progress
    again = c.post(f"/work-items/{task_id}/runs")
    assert again.status_code == 409


def test_start_run_on_missing_task_404():
    c = make_client()
    assert c.post("/work-items/nope/runs").status_code == 404


def test_start_run_on_non_task_kind_404():
    c = make_client()
    pid = c.post("/projects", json={"name": "p", "repo_url": "r"}).json()["data"]["id"]
    epic = c.post(f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E"}).json()["data"]
    assert c.post(f"/work-items/{epic['id']}/runs").status_code == 404


def test_start_run_without_team_assigned_409():
    c = make_client()
    pid = c.post("/projects", json={"name": "p", "repo_url": "r"}).json()["data"]["id"]
    epic = c.post(f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E"}).json()["data"]
    feat = c.post(
        f"/projects/{pid}/work-items",
        json={"kind": "feature", "title": "F", "parent_id": epic["id"]},
    ).json()["data"]
    task = c.post(
        f"/projects/{pid}/work-items",
        json={"kind": "task", "title": "T", "parent_id": feat["id"]},
    ).json()["data"]
    c.post(f"/work-items/{task['id']}/status", json={"status": "ready"})

    resp = c.post(f"/work-items/{task['id']}/runs")
    assert resp.status_code == 409
    assert resp.json()["error"] == "project has no team assigned"


def test_get_missing_run_404():
    c = make_client()
    assert c.get("/runs/nope").status_code == 404


def _start_run(c: TestClient) -> dict:
    task_id, _team_id, _pid = _ready_task(c)
    return c.post(f"/work-items/{task_id}/runs").json()["data"]


def test_cancel_run_moves_it_to_cancelled():
    c = make_client()
    run = _start_run(c)
    resp = c.post(f"/runs/{run['id']}/cancel")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "cancelled"


def test_cancel_unknown_run_is_404():
    c = make_client()
    resp = c.post("/runs/deadbeef/cancel")
    assert resp.status_code == 404


def _seed_awaiting_run(c: TestClient) -> str:
    task_id, team_id, _pid = _ready_task(c)
    uow = SqlUnitOfWork(c.app.state.session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        run = uow.runs.create(
            Run(owner_id="dev-user", task_id=task_id, team_id=team_id,
                status=RunStatus.AWAITING_APPROVAL)
        )
    return run.id


def test_approve_gate_moves_run_to_done():
    c = make_client()
    run_id = _seed_awaiting_run(c)
    resp = c.post(f"/runs/{run_id}/approve")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "done"


def test_reject_gate_moves_run_to_failed():
    c = make_client()
    run_id = _seed_awaiting_run(c)
    resp = c.post(f"/runs/{run_id}/reject")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "failed"


def test_approve_pending_run_is_409():
    c = make_client()
    run = _start_run(c)
    resp = c.post(f"/runs/{run['id']}/approve")
    assert resp.status_code == 409


def test_patch_run_edits_metadata_only():
    c = make_client()
    run = _start_run(c)
    resp = c.patch(f"/runs/{run['id']}", json={"branch": "agent/x", "stage": "implement"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["branch"] == "agent/x"
    assert data["stage"] == "implement"
    assert data["status"] == "pending"


def test_patch_run_ignores_status_field():
    c = make_client()
    run = _start_run(c)
    resp = c.patch(f"/runs/{run['id']}", json={"status": "done"})
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "pending"
