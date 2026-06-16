from fastapi.testclient import TestClient

from adapters.database.uow import SqlUnitOfWork
from domain.models import AgentRole, RoleMemoryEntry
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
    resp = c.get("/role-memory?role=backend")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [e["content"] for e in data] == ["newer", "older"]
    assert resp.json()["meta"]["total"] == 2
