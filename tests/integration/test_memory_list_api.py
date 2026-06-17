# tests/integration/test_memory_list_api.py
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
    from domain.memory import MemoryProposal, MemoryProposalStatus
    uow = SqlUnitOfWork(app.state.session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        uow.memory_proposals.create(MemoryProposal(
            owner_id="dev-user", run_id="r1", project_id="p1", branch="b1",
            diff="--- a\n+++ b\n", files=["CLAUDE.md"],
            status=MemoryProposalStatus.PROPOSED))
        uow.memory_proposals.create(MemoryProposal(
            owner_id="dev-user", run_id="r2", project_id="p1", branch="b2",
            diff="--- a\n+++ b\n", files=["AGENTS.md"],
            status=MemoryProposalStatus.APPLIED))
        uow.memory_proposals.create(MemoryProposal(
            owner_id="dev-user", run_id="r3", project_id="p2", branch="b3",
            diff="--- a\n+++ b\n", files=["docs/adr"],
            status=MemoryProposalStatus.REJECTED))


def test_memory_lists_all_owner_proposals():
    client = _client()
    _seed(client)
    body = client.get("/memory-proposals").json()
    assert body["success"] is True
    assert body["meta"]["total"] == 3


def test_memory_filters_by_project():
    client = _client()
    _seed(client)
    data = client.get("/memory-proposals", params={"project_id": "p2"}).json()["data"]
    assert len(data) == 1
    assert data[0]["status"] == "rejected"


def test_memory_filters_by_status():
    client = _client()
    _seed(client)
    data = client.get("/memory-proposals", params={"status": "applied"}).json()["data"]
    assert len(data) == 1
    assert data[0]["files"] == ["AGENTS.md"]


def test_memory_rejects_bad_status():
    client = _client()
    assert client.get("/memory-proposals", params={"status": "nope"}).status_code == 422


def test_memory_paginates():
    client = _client()
    _seed(client)
    body = client.get("/memory-proposals", params={"page_size": 2}).json()
    assert len(body["data"]) == 2
    assert body["meta"]["total"] == 3


def test_memory_empty():
    client = _client()
    body = client.get("/memory-proposals").json()
    assert body["data"] == []


def test_memory_excludes_other_owner_proposals():
    client = _client()
    _seed(client)
    app = client.app
    from adapters.database.uow import SqlUnitOfWork
    from domain.memory import MemoryProposal, MemoryProposalStatus
    other = SqlUnitOfWork(app.state.session_factory, required_filters={"owner_id": "other-user"})
    with other.transaction():
        other.memory_proposals.create(MemoryProposal(
            owner_id="other-user", run_id="ro", project_id="po", branch="bo",
            diff="--- a\n+++ b\n", files=["OTHER.md"],
            status=MemoryProposalStatus.PROPOSED))
    body = client.get("/memory-proposals").json()
    assert body["meta"]["total"] == 3
    assert all(p["run_id"] != "ro" for p in body["data"])
