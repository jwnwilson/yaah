import pytest

from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.projects import Project
from domain.runs import Run


def _uow(owner: str = "u1") -> SqlUnitOfWork:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return SqlUnitOfWork(make_session_factory(engine), required_filters={"owner_id": owner})


def test_transaction_commits_across_repositories():
    uow = _uow()
    with uow.transaction():
        p = uow.projects.create(Project(owner_id="u1", name="p", repo_url="r"))
        uow.runs.create(Run(owner_id="u1", task_id="t1", team_id="tm1"))
    with uow.transaction():
        assert uow.projects.get(p.id).name == "p"
        assert uow.runs.list(filters={"task_id": "t1"}).total == 1


def test_transaction_rolls_back_all_writes_on_error():
    uow = _uow()
    with pytest.raises(RuntimeError):
        with uow.transaction():
            uow.projects.create(Project(owner_id="u1", name="p", repo_url="r"))
            raise RuntimeError("boom")
    with uow.transaction():
        assert uow.projects.list().total == 0


def test_repository_access_outside_transaction_fails():
    uow = _uow()
    with pytest.raises(RuntimeError):
        _ = uow.projects


def test_nested_transaction_rejected():
    uow = _uow()
    with uow.transaction():
        with pytest.raises(RuntimeError):
            with uow.transaction():
                pass
