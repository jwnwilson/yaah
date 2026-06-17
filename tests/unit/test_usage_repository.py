import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.errors import IntegrityConflict
from domain.runs import RunStage
from domain.usage import UsageRecord


@pytest.fixture
def uow():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    return SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})


def _rec(**kw):
    base = dict(owner_id="dev-user", run_id="r1", work_item_id="t1", project_id="p1",
                stage=RunStage.IMPLEMENT, model_id="m1", input_tokens=10, cost_usd=0.1)
    base.update(kw)
    return UsageRecord(**base)


def test_create_and_list_usage_record(uow):
    with uow.transaction():
        uow.usage.create(_rec())
        page = uow.usage.list(filters={"run_id": "r1"})
    assert page.total == 1
    assert page.results[0].input_tokens == 10


def test_duplicate_dedupe_key_raises_integrity_conflict(uow):
    with uow.transaction():
        uow.usage.create(_rec())
    with pytest.raises(IntegrityConflict):
        with uow.transaction():
            uow.usage.create(_rec())  # same run/stage/role/model -> same dedupe_key


def test_owner_scoping_hides_other_tenants(uow):
    with uow.transaction():
        uow.usage.create(_rec(owner_id="dev-user"))
    other = SqlUnitOfWork(uow._session_factory, required_filters={"owner_id": "someone-else"})
    with other.transaction():
        page = other.usage.list(filters={"run_id": "r1"})
    assert page.total == 0
