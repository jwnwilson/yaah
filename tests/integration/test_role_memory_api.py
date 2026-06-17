from fastapi.testclient import TestClient

from adapters.database.uow import SqlUnitOfWork
from domain.agent.memory import RoleMemoryEntry
from domain.agent.models import AgentRole
from interactors.api.app import create_app
from interactors.api.settings import Settings


def _client():
    app = create_app(Settings(_env_file=None, database_url="sqlite:///:memory:"))
    return app, TestClient(app)


def test_list_role_memory_owner_scoped_newest_first():
    app, c = _client()
    factory = app.state.session_factory
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        uow.role_memory.create(RoleMemoryEntry(owner_id="dev-user", role=AgentRole.BACKEND,
                                               content="older", project_id="p1"))
        uow.role_memory.create(RoleMemoryEntry(owner_id="dev-user", role=AgentRole.BACKEND,
                                               content="newer", project_id="p2"))
        uow.role_memory.create(RoleMemoryEntry(owner_id="dev-user", role=AgentRole.QA,
                                               content="qa", project_id="p1"))
    other = SqlUnitOfWork(factory, required_filters={"owner_id": "someone-else"})
    with other.transaction():
        other.role_memory.create(RoleMemoryEntry(owner_id="someone-else",
                                                 role=AgentRole.BACKEND, content="not mine"))
    resp = c.get("/role-memory?role=backend")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [e["content"] for e in data] == ["newer", "older"]
    assert "not mine" not in [e["content"] for e in data]
    assert resp.json()["meta"]["total"] == 2


def test_role_memory_invalid_role_returns_422():
    _, c = _client()
    assert c.get("/role-memory?role=wizard").status_code == 422


def test_role_memory_project_id_filter():
    app, c = _client()
    factory = app.state.session_factory
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        uow.role_memory.create(RoleMemoryEntry(owner_id="dev-user", role=AgentRole.BACKEND,
                                               content="from-p1", project_id="p1"))
        uow.role_memory.create(RoleMemoryEntry(owner_id="dev-user", role=AgentRole.BACKEND,
                                               content="from-p2", project_id="p2"))
    resp = c.get("/role-memory?role=backend&project_id=p1")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [e["content"] for e in data] == ["from-p1"]
    assert resp.json()["meta"]["total"] == 1
