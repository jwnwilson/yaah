# tests/integration/test_usage_global_api.py
from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def _client():
    return TestClient(
        create_app(Settings(_env_file=None, database_url="sqlite:///:memory:", auth_mode="dev"))
    )


def _seed(client):
    app = client.app
    from adapters.database.uow import SqlUnitOfWork
    from domain.projects import Project, WorkItem, WorkItemKind
    from domain.runs import Run, RunStage
    from domain.usage import UsageRecord
    uow = SqlUnitOfWork(app.state.session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        for pid in ("p1", "p2"):
            uow.projects.create(Project(id=pid, owner_id="dev-user", name=pid, local_path="/x"))
            uow.work_items.create(WorkItem(id=f"t-{pid}", owner_id="dev-user", project_id=pid,
                                           kind=WorkItemKind.TASK, parent_id=f"parent-{pid}",
                                           title="T"))
            uow.runs.create(Run(id=f"r-{pid}", owner_id="dev-user",
                                task_id=f"t-{pid}", team_id="tm"))
        uow.usage.create(UsageRecord(owner_id="dev-user", run_id="r-p1", work_item_id="t-p1",
                                     project_id="p1", stage=RunStage.PLAN, model_id="m1",
                                     input_tokens=10, output_tokens=2, cost_usd=0.1))
        uow.usage.create(UsageRecord(owner_id="dev-user", run_id="r-p2", work_item_id="t-p2",
                                     project_id="p2", stage=RunStage.IMPLEMENT, model_id="m2",
                                     input_tokens=90, output_tokens=8, cost_usd=0.4))


def test_global_usage_rolls_up_all_projects():
    client = _client()
    _seed(client)
    body = client.get("/usage").json()
    assert body["success"] is True
    assert body["data"]["totals"]["input_tokens"] == 100
    assert round(body["data"]["totals"]["cost_usd"], 2) == 0.5


def test_global_usage_filters_by_project():
    client = _client()
    _seed(client)
    data = client.get("/usage", params={"project_id": "p1"}).json()["data"]
    assert data["totals"]["input_tokens"] == 10


def test_global_usage_groups_by_model():
    client = _client()
    _seed(client)
    data = client.get("/usage", params={"group_by": "model"}).json()["data"]
    assert data["group_by"] == "model"
    assert data["groups"]["m1"]["input_tokens"] == 10
    assert data["groups"]["m2"]["input_tokens"] == 90


def test_global_usage_rejects_bad_group():
    client = _client()
    assert client.get("/usage", params={"group_by": "nope"}).status_code == 422


def test_global_usage_rejects_inverted_range():
    client = _client()
    resp = client.get("/usage", params={"since": "2026-02-01T00:00:00Z",
                                        "until": "2026-01-01T00:00:00Z"})
    assert resp.status_code == 422


def test_global_usage_empty_is_zero():
    client = _client()
    data = client.get("/usage").json()["data"]
    assert data["totals"]["total_tokens"] == 0


def test_global_usage_includes_records_within_time_window():
    client = _client()
    _seed(client)
    data = client.get("/usage", params={"since": "2000-01-01T00:00:00Z",
                                        "until": "2999-01-01T00:00:00Z"}).json()["data"]
    assert data["totals"]["input_tokens"] == 100


def test_global_usage_excludes_other_owner_records():
    client = _client()
    _seed(client)
    app = client.app
    from adapters.database.uow import SqlUnitOfWork
    from domain.projects import Project, WorkItem, WorkItemKind
    from domain.runs import Run, RunStage
    from domain.usage import UsageRecord
    other = SqlUnitOfWork(app.state.session_factory, required_filters={"owner_id": "other-user"})
    with other.transaction():
        other.projects.create(Project(id="po", owner_id="other-user", name="po", local_path="/x"))
        other.work_items.create(WorkItem(id="t-po", owner_id="other-user", project_id="po",
                                         kind=WorkItemKind.TASK, parent_id="parent-po", title="T"))
        other.runs.create(Run(id="r-po", owner_id="other-user", task_id="t-po", team_id="tm"))
        other.usage.create(UsageRecord(owner_id="other-user", run_id="r-po", work_item_id="t-po",
                                       project_id="po", stage=RunStage.PLAN, model_id="mo",
                                       input_tokens=500, output_tokens=50, cost_usd=5.0))
    data = client.get("/usage").json()["data"]
    assert data["totals"]["input_tokens"] == 100
