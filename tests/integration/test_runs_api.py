from fastapi.testclient import TestClient

from adapters.database.uow import SqlUnitOfWork
from domain.models import Run, RunStatus
from interactors.api.app import create_app
from interactors.api.deps import temporal_client
from interactors.api.settings import Settings


def make_client() -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, database_url="sqlite:///:memory:")))


class _FakeTemporal:
    def __init__(self):
        self.started = []
        self.signals = []

    def start_run_workflow(self, run_input):
        self.started.append(run_input)

    def signal(self, run_id, name):
        self.signals.append((run_id, name))


def _client_with_fake_temporal():
    app = create_app(Settings(_env_file=None, database_url="sqlite:///:memory:"))
    fake = _FakeTemporal()
    app.dependency_overrides[temporal_client] = lambda: fake
    return TestClient(app), fake


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


def _seed_awaiting_run(c: TestClient) -> str:
    task_id, team_id, _pid = _ready_task(c)
    uow = SqlUnitOfWork(c.app.state.session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        run = uow.runs.create(
            Run(owner_id="dev-user", task_id=task_id, team_id=team_id,
                status=RunStatus.AWAITING_APPROVAL)
        )
    return run.id


def test_start_run_on_ready_task():
    c, _fake = _client_with_fake_temporal()
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
    c, _fake = _client_with_fake_temporal()
    task_id, _, _ = _ready_task(c)
    c.post(f"/work-items/{task_id}/runs")  # consumes ready -> in_progress
    again = c.post(f"/work-items/{task_id}/runs")
    assert again.status_code == 409


def test_start_run_on_missing_task_404():
    c, _fake = _client_with_fake_temporal()
    assert c.post("/work-items/nope/runs").status_code == 404


def test_start_run_on_non_task_kind_404():
    c, _fake = _client_with_fake_temporal()
    pid = c.post("/projects", json={"name": "p", "repo_url": "r"}).json()["data"]["id"]
    epic = c.post(f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E"}).json()["data"]
    assert c.post(f"/work-items/{epic['id']}/runs").status_code == 404


def test_start_run_without_team_assigned_409():
    c, _fake = _client_with_fake_temporal()
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
    c, _fake = _client_with_fake_temporal()
    assert c.get("/runs/nope").status_code == 404


def _start_run(c: TestClient) -> dict:
    """Start a run; c must already have a fake temporal override."""
    task_id, _team_id, _pid = _ready_task(c)
    return c.post(f"/work-items/{task_id}/runs").json()["data"]


def test_cancel_unknown_run_is_404():
    c, _fake = _client_with_fake_temporal()
    resp = c.post("/runs/deadbeef/cancel")
    assert resp.status_code == 404


def test_patch_run_edits_metadata_only():
    c, fake = _client_with_fake_temporal()
    run = _start_run(c)
    resp = c.patch(f"/runs/{run['id']}", json={"branch": "agent/x", "stage": "implement"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["branch"] == "agent/x"
    assert data["stage"] == "implement"
    assert data["status"] == "pending"


def test_patch_run_ignores_status_field():
    c, fake = _client_with_fake_temporal()
    run = _start_run(c)
    resp = c.patch(f"/runs/{run['id']}", json={"status": "done"})
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "pending"


# --- A3 new tests: workflow + signal behaviour ---

def test_start_run_starts_workflow():
    c, fake = _client_with_fake_temporal()
    task_id, _team, _pid = _ready_task(c)
    resp = c.post(f"/work-items/{task_id}/runs")
    assert resp.status_code == 201
    assert len(fake.started) == 1
    assert fake.started[0]["run_id"] == resp.json()["data"]["id"]


def test_approve_sends_signal_only_when_awaiting():
    c, fake = _client_with_fake_temporal()
    run_id = _seed_awaiting_run(c)
    resp = c.post(f"/runs/{run_id}/approve")
    assert resp.status_code == 202
    assert (run_id, "approve") in fake.signals


def test_approve_pending_run_is_409():
    c, fake = _client_with_fake_temporal()
    task_id, _t, _p = _ready_task(c)
    run_id = c.post(f"/work-items/{task_id}/runs").json()["data"]["id"]  # pending
    resp = c.post(f"/runs/{run_id}/approve")
    assert resp.status_code == 409
    assert fake.signals == []


def test_reject_sends_signal_only_when_awaiting():
    c, fake = _client_with_fake_temporal()
    run_id = _seed_awaiting_run(c)
    resp = c.post(f"/runs/{run_id}/reject")
    assert resp.status_code == 202
    assert (run_id, "reject") in fake.signals


def test_cancel_sends_signal_for_active_run():
    c, fake = _client_with_fake_temporal()
    task_id, _t, _p = _ready_task(c)
    run_id = c.post(f"/work-items/{task_id}/runs").json()["data"]["id"]  # pending
    resp = c.post(f"/runs/{run_id}/cancel")
    assert resp.status_code == 202
    assert (run_id, "cancel") in fake.signals


def test_cancel_terminal_run_is_409():
    c, fake = _client_with_fake_temporal()
    run_id = _seed_awaiting_run(c)
    # Manually make it done via DB
    uow = SqlUnitOfWork(c.app.state.session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        run = uow.runs.get(run_id)
        uow.runs.update(run_id, run.model_copy(update={"status": RunStatus.DONE}))
    resp = c.post(f"/runs/{run_id}/cancel")
    assert resp.status_code == 409


def test_list_run_events():
    c, fake = _client_with_fake_temporal()
    run_id = _seed_awaiting_run(c)
    resp = c.get(f"/runs/{run_id}/events")
    assert resp.status_code == 200
    assert "data" in resp.json()


def test_start_run_passes_profile_and_repo(monkeypatch):
    c, fake = _client_with_fake_temporal()
    task_id, _t, _pid = _ready_task(c)
    c.post(f"/work-items/{task_id}/runs")
    assert fake.started[0]["profile"] in ("local", "remote")
    assert "repo_ref" in fake.started[0]
