import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.base import utc_now
from domain.memory import MemoryProposal, MemoryProposalStatus


@pytest.fixture
def factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_memory_proposal_apply_fields_round_trip(factory):
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    resolved = utc_now()
    with uow.transaction():
        created = uow.memory_proposals.create(MemoryProposal(
            owner_id="u1", run_id="r1", project_id="p1", branch="b",
            status=MemoryProposalStatus.APPLIED, pr_url="http://pr/1", resolved_at=resolved))
    with uow.transaction():
        fetched = uow.memory_proposals.get(created.id)
    assert fetched.status == "applied"
    assert fetched.pr_url == "http://pr/1"
    assert fetched.resolved_at is not None


def test_memory_proposal_round_trips(factory):
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        created = uow.memory_proposals.create(MemoryProposal(
            owner_id="u1", run_id="r1", project_id="p1", branch="agent/memory-r1",
            diff="diff --git a/CLAUDE.md b/CLAUDE.md", files=["CLAUDE.md"]))
    with uow.transaction():
        fetched = uow.memory_proposals.get(created.id)
    assert fetched.run_id == "r1"
    assert fetched.files == ["CLAUDE.md"]
    assert fetched.status == "proposed"


def test_memory_proposal_is_owner_scoped(factory):
    owner_uow = SqlUnitOfWork(factory, required_filters={"owner_id": "owner"})
    with owner_uow.transaction():
        owner_uow.memory_proposals.create(MemoryProposal(
            owner_id="owner", run_id="r1", project_id="p1", branch="b"))
    other_uow = SqlUnitOfWork(factory, required_filters={"owner_id": "intruder"})
    with other_uow.transaction():
        results = other_uow.memory_proposals.list(filters={"run_id": "r1"}).results
    assert results == []
