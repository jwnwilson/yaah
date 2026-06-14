from fastapi.testclient import TestClient

from adapters.database.uow import SqlUnitOfWork
from domain.models import MemoryProposal, Run
from interactors.api.app import create_app
from interactors.api.settings import Settings


def make_client() -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, database_url="sqlite:///:memory:")))


def _seed_run(c: TestClient) -> str:
    uow = SqlUnitOfWork(c.app.state.session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        run = uow.runs.create(Run(owner_id="dev-user", task_id="t1", team_id="tm1"))
    return run.id


def _seed_proposal(c: TestClient, run_id: str) -> None:
    uow = SqlUnitOfWork(c.app.state.session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        uow.memory_proposals.create(MemoryProposal(
            owner_id="dev-user", run_id=run_id, project_id="p1",
            branch=f"agent/memory-{run_id}",
            diff="diff --git a/CLAUDE.md b/CLAUDE.md", files=["CLAUDE.md"]))


def test_get_run_memory_returns_the_proposal():
    c = make_client()
    run_id = _seed_run(c)
    _seed_proposal(c, run_id)
    resp = c.get(f"/runs/{run_id}/memory")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["branch"] == f"agent/memory-{run_id}"
    assert body["data"]["files"] == ["CLAUDE.md"]


def test_get_run_memory_returns_null_when_absent():
    c = make_client()
    run_id = _seed_run(c)
    resp = c.get(f"/runs/{run_id}/memory")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"] is None


def test_get_run_memory_404_for_unknown_run():
    c = make_client()
    resp = c.get("/runs/doesnotexist/memory")
    assert resp.status_code == 404
    assert resp.json()["success"] is False
