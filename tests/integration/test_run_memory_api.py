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


def _seed_project(c: TestClient) -> None:
    from domain.models import Project
    uow = SqlUnitOfWork(c.app.state.session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        uow.projects.create(Project(id="p1", owner_id="dev-user", name="P", local_path="/x"))


def _client_with_fake_applier() -> TestClient:
    from adapters.git.fake import FakeGit, FakeGitForge
    from interactors.api.deps import memory_applier
    from interactors.memory_apply import MemoryApplier
    app = create_app(Settings(_env_file=None, database_url="sqlite:///:memory:"))
    app.dependency_overrides[memory_applier] = lambda: MemoryApplier(
        FakeGit(), FakeGitForge(), profile="local")
    return TestClient(app)


def test_apply_run_memory_marks_applied():
    c = _client_with_fake_applier()
    _seed_project(c)
    run_id = _seed_run(c)
    _seed_proposal(c, run_id)
    resp = c.post(f"/runs/{run_id}/memory/apply")
    assert resp.status_code == 202
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["status"] == "applied"
    # second apply -> 409 (no longer proposed)
    assert c.post(f"/runs/{run_id}/memory/apply").status_code == 409


def test_reject_run_memory_marks_rejected():
    c = make_client()
    run_id = _seed_run(c)
    _seed_proposal(c, run_id)
    resp = c.post(f"/runs/{run_id}/memory/reject")
    assert resp.status_code == 202
    body = resp.json()
    assert body["data"]["status"] == "rejected"
    assert body["data"]["resolved_at"] is not None


def test_apply_run_memory_404_when_absent():
    c = _client_with_fake_applier()
    run_id = _seed_run(c)
    assert c.post(f"/runs/{run_id}/memory/apply").status_code == 404
