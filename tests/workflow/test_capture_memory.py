import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from adapters.git.fake import FakeGit
from adapters.storage.local import LocalStorageAdapter
from domain.projects import Project
from domain.runs import Run
from domain.work_items import WorkItem, WorkItemKind, WorkItemStatus
from interactors.temporal.activities import RunActivities


@pytest.fixture
def factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _seed(factory):
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        uow.projects.create(Project(id="p1", owner_id="dev-user", name="P", local_path="/x"))
        uow.work_items.create(WorkItem(id="t1", owner_id="dev-user", project_id="p1",
                                       kind=WorkItemKind.TASK, parent_id="f1", title="T",
                                       status=WorkItemStatus.IN_PROGRESS))
        uow.runs.create(Run(id="r1", owner_id="dev-user", task_id="t1", team_id="tm"))


def _acts(factory, git, tmp):
    return RunActivities(factory, runtime=None,
                         storage=LocalStorageAdapter(base_dir=tmp),
                         git=git, forge=None)


def test_capture_memory_persists_proposal_and_event(factory):
    _seed(factory)
    with tempfile.TemporaryDirectory() as tmp:
        git = FakeGit(memory_diff="diff --git a/CLAUDE.md b/CLAUDE.md\n+++ b/CLAUDE.md\n+x\n")
        acts = _acts(factory, git, tmp)
        result = acts.capture_memory({"run_id": "r1", "owner_id": "dev-user",
                                      "project_id": "p1", "base": "main", "profile": "local"})
    assert result["proposal_id"] is not None
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        proposals = uow.memory_proposals.list(filters={"run_id": "r1"}).results
        events = uow.run_events.list(filters={"run_id": "r1"}).results
    assert len(proposals) == 1
    assert proposals[0].branch == "agent/memory-r1"
    assert proposals[0].files == ["CLAUDE.md"]
    assert git.committed_to_branch[0][1] == "agent/memory-r1"
    assert any("memory proposal" in e.message for e in events)


def test_capture_memory_noop_when_no_memory_changes(factory):
    _seed(factory)
    with tempfile.TemporaryDirectory() as tmp:
        git = FakeGit(memory_diff="")  # no memory edits
        acts = _acts(factory, git, tmp)
        result = acts.capture_memory({"run_id": "r1", "owner_id": "dev-user",
                                      "project_id": "p1", "base": "main", "profile": "local"})
    assert result["proposal_id"] is None
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        proposals = uow.memory_proposals.list(filters={"run_id": "r1"}).results
    assert proposals == []
    assert git.committed_to_branch == []


_DIFF = "diff --git a/CLAUDE.md b/CLAUDE.md\n+++ b/CLAUDE.md\n+x\n"


def test_capture_memory_auto_applies_in_full_auto(factory):
    _seed(factory)
    with tempfile.TemporaryDirectory() as tmp:
        git = FakeGit(memory_diff=_DIFF)
        acts = _acts(factory, git, tmp)
        acts.capture_memory({"run_id": "r1", "owner_id": "dev-user", "project_id": "p1",
                             "base": "main", "profile": "local", "autonomy": "full_auto",
                             "repo_ref": "/repo"})
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        proposal = uow.memory_proposals.list(filters={"run_id": "r1"}).results[0]
    assert proposal.status == "applied"
    assert proposal.resolved_at is not None
    assert git.merged_into_base == [("/repo", "agent/memory-r1", "main")]


def test_capture_memory_stays_proposed_when_gated(factory):
    _seed(factory)
    with tempfile.TemporaryDirectory() as tmp:
        git = FakeGit(memory_diff=_DIFF)
        acts = _acts(factory, git, tmp)
        acts.capture_memory({"run_id": "r1", "owner_id": "dev-user", "project_id": "p1",
                             "base": "main", "profile": "local", "autonomy": "gated_all",
                             "repo_ref": "/repo"})
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        proposal = uow.memory_proposals.list(filters={"run_id": "r1"}).results[0]
    assert proposal.status == "proposed"
    assert git.merged_into_base == []
