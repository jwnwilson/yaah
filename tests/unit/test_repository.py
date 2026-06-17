import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from adapters.database.orm import Base, ProjectRow
from adapters.database.repository import SqlRepository
from domain.errors import InvalidFilter, RecordNotFound
from domain.projects import Project


class ProjectRepo(SqlRepository[Project]):
    orm_model = ProjectRow
    dto = Project


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as s:
        yield s


def _repo(session: Session, owner: str | None = "u1") -> ProjectRepo:
    required = {"owner_id": owner} if owner else None
    return ProjectRepo(session, required_filters=required)


def _project(name: str, owner: str = "u1") -> Project:
    return Project(owner_id=owner, name=name, repo_url="r")


def test_create_get_roundtrip(session):
    repo = _repo(session)
    created = repo.create(_project("a"))
    assert repo.get(created.id).name == "a"


def test_get_missing_raises_record_not_found(session):
    with pytest.raises(RecordNotFound):
        _repo(session).get("nope")


def test_required_filters_scope_get_and_list(session):
    repo_u1 = _repo(session, "u1")
    p = repo_u1.create(_project("mine"))
    repo_u2 = _repo(session, "u2")
    with pytest.raises(RecordNotFound):
        repo_u2.get(p.id)
    assert repo_u2.list().total == 0
    assert repo_u1.list().total == 1


def test_filter_dsl(session):
    repo = _repo(session)
    a = repo.create(_project("alpha"))
    repo.create(_project("beta"))
    assert repo.list(filters={"name": "alpha"}).results[0].id == a.id
    assert repo.list(filters={"name__in": ["alpha"]}).total == 1
    assert repo.list(filters={"name__like": "ALP"}).total == 1
    assert repo.list(filters={"team_id__isnull": True}).total == 2
    assert repo.list(filters={"name__ne": "alpha"}).results[0].name == "beta"


def test_invalid_filter_key_raises(session):
    with pytest.raises(InvalidFilter):
        _repo(session).list(filters={"nope": 1})


def test_pagination_and_order(session):
    repo = _repo(session)
    for n in ["a", "b", "c"]:
        repo.create(_project(n))
    page = repo.list(page_size=2, page_number=2, order_by="name")
    assert page.total == 3
    assert [p.name for p in page.results] == ["c"]
    assert repo.list(order_by="-name").results[0].name == "c"


def test_update_copies_fields_but_not_owner(session):
    repo = _repo(session)
    p = repo.create(_project("a"))
    hijack = p.model_copy(update={"name": "b", "owner_id": "evil"})
    updated = repo.update(p.id, hijack)
    assert updated.name == "b"
    assert updated.owner_id == "u1"


def test_delete_and_delete_many(session):
    repo = _repo(session)
    p = repo.create(_project("a"))
    repo.create(_project("b"))
    repo.delete(p.id)
    with pytest.raises(RecordNotFound):
        repo.get(p.id)
    assert repo.delete_many({"name": "b"}) == 1
    assert repo.list().total == 0
