from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.agent.models import AgentRole
from domain.memory import RoleMemoryEntry


def _factory():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def test_role_memory_append_project_and_cross_project_queries():
    factory = _factory()
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        uow.role_memory.create(RoleMemoryEntry(owner_id="u1", role=AgentRole.BACKEND,
                                               content="p1 note", project_id="p1"))
        uow.role_memory.create(RoleMemoryEntry(owner_id="u1", role=AgentRole.BACKEND,
                                               content="p2 note", project_id="p2"))
        uow.role_memory.create(RoleMemoryEntry(owner_id="u1", role=AgentRole.QA,
                                               content="qa note", project_id="p1"))
    with uow.transaction():
        proj = uow.role_memory.list(filters={"role": "backend", "project_id": "p1"}).results
        allp = uow.role_memory.list(filters={"role": "backend"},
                                    order_by="-created_at").results
    assert {e.content for e in proj} == {"p1 note"}
    assert {e.content for e in allp} == {"p1 note", "p2 note"}


def test_role_memory_owner_isolation():
    factory = _factory()
    a = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    b = SqlUnitOfWork(factory, required_filters={"owner_id": "u2"})
    with a.transaction():
        a.role_memory.create(RoleMemoryEntry(owner_id="u1", role=AgentRole.BACKEND, content="x"))
    with b.transaction():
        assert b.role_memory.list(filters={"role": "backend"}).total == 0
