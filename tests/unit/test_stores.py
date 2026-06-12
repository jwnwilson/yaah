import pytest

from adapters.database.engine import make_engine, make_session_factory
from adapters.database.stores import SqlProjectStore, SqlWorkItemStore
from adapters.database.tables import metadata
from domain.models import Project, WorkItem, WorkItemKind, WorkItemStatus


@pytest.fixture()
def session_factory():
    engine = make_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    return make_session_factory(engine)


def test_project_roundtrip_and_owner_scoping(session_factory):
    store = SqlProjectStore(session_factory)
    p = store.add(Project(owner_id="u1", name="llm_api", repo_url="https://github.com/x/y"))
    assert store.get(p.id, owner_id="u1").name == "llm_api"
    assert store.get(p.id, owner_id="someone-else") is None
    assert [x.id for x in store.list("u1")] == [p.id]


def test_project_update_and_delete(session_factory):
    store = SqlProjectStore(session_factory)
    p = store.add(Project(owner_id="u1", name="a", repo_url="r"))
    p = p.model_copy(update={"name": "b"})
    assert store.update(p).name == "b"
    assert store.delete(p.id, owner_id="u1") is True
    assert store.get(p.id, owner_id="u1") is None


def test_work_item_filters(session_factory):
    store = SqlWorkItemStore(session_factory)
    epic = store.add(WorkItem(project_id="p1", kind=WorkItemKind.EPIC, title="E"))
    task = store.add(
        WorkItem(
            project_id="p1",
            kind=WorkItemKind.TASK,
            parent_id=epic.id,
            title="T",
            status=WorkItemStatus.READY,
        )
    )
    assert [i.id for i in store.list("p1", kind=WorkItemKind.TASK)] == [task.id]
    assert [i.id for i in store.list("p1", status=WorkItemStatus.READY)] == [task.id]
    assert [i.id for i in store.list("p1", parent_id=epic.id)] == [task.id]
    assert len(store.list("p1")) == 2
