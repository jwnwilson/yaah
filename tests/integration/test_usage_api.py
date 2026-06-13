from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def _client():
    return TestClient(
        create_app(Settings(_env_file=None, database_url="sqlite:///:memory:", auth_mode="dev"))
    )


def _seed_run_with_usage(client):
    app = client.app
    from adapters.database.uow import SqlUnitOfWork
    from domain.models import Project, Run, RunStage, UsageRecord, WorkItem, WorkItemKind
    uow = SqlUnitOfWork(app.state.session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        uow.projects.create(Project(id="p1", owner_id="dev-user", name="P", local_path="/x"))
        uow.work_items.create(WorkItem(id="e1", owner_id="dev-user", project_id="p1",
                                       kind=WorkItemKind.EPIC, title="E"))
        uow.work_items.create(WorkItem(id="f1", owner_id="dev-user", project_id="p1",
                                       kind=WorkItemKind.FEATURE, parent_id="e1", title="F"))
        uow.work_items.create(WorkItem(id="t1", owner_id="dev-user", project_id="p1",
                                       kind=WorkItemKind.TASK, parent_id="f1", title="T"))
        uow.runs.create(Run(id="r1", owner_id="dev-user", task_id="t1", team_id="tm"))
        uow.usage.create(UsageRecord(owner_id="dev-user", run_id="r1", work_item_id="t1",
                                     project_id="p1", stage=RunStage.PLAN, model_id="m1",
                                     input_tokens=10, output_tokens=2, cost_usd=0.1))
        uow.usage.create(UsageRecord(owner_id="dev-user", run_id="r1", work_item_id="t1",
                                     project_id="p1", stage=RunStage.IMPLEMENT, model_id="m1",
                                     input_tokens=90, output_tokens=8, cost_usd=0.4))


def test_run_usage_returns_totals_and_breakdown():
    client = _client()
    _seed_run_with_usage(client)
    resp = client.get("/runs/r1/usage")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["totals"]["input_tokens"] == 100
    assert round(body["data"]["totals"]["cost_usd"], 2) == 0.5
    stages = {b["stage"] for b in body["data"]["breakdown"]}
    assert stages == {"plan", "implement"}
