import tempfile

from adapters.agent.runtime.fake import FakeAgentRuntime
from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from adapters.git.fake import FakeGit, FakeGitForge
from adapters.storage.local import LocalStorageAdapter
from domain.models import (
    Project,
    Run,
    RunStage,
    RunStatus,
    WorkItem,
    WorkItemKind,
    WorkItemStatus,
)
from interactors.temporal.activities import RunActivities


def _factory():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def _storage():
    return LocalStorageAdapter(base_dir=tempfile.mkdtemp())


def _seed_run(factory) -> str:
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        uow.projects.create(Project(id="p1", owner_id="u1", name="P", local_path="/tmp/x"))
        uow.work_items.create(WorkItem(id="t1", owner_id="u1", project_id="p1",
                                       kind=WorkItemKind.TASK, parent_id="f1", title="T",
                                       status=WorkItemStatus.IN_PROGRESS))
        run = uow.runs.create(Run(owner_id="u1", task_id="t1", team_id="tm1"))
    return run.id


def _acts(factory, *, git=None, forge=None, has_changes=True):
    storage = LocalStorageAdapter(base_dir=tempfile.mkdtemp())
    return RunActivities(factory, FakeAgentRuntime(storage=storage), storage,
                         git or FakeGit(has_changes=has_changes), forge or FakeGitForge())


def test_persist_run_state_updates_row():
    factory = _factory()
    run_id = _seed_run(factory)
    acts = _acts(factory)
    acts.persist_run_state(
        {
            "run_id": run_id,
            "owner_id": "u1",
            "status": RunStatus.RUNNING,
            "stage": RunStage.PLAN,
            "cost_usd": 1.0,
        }
    )
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        run = uow.runs.get(run_id)
    assert run.status == "running" and run.stage == "plan" and run.cost_usd == 1.0


def test_cleanup_workspace_deletes_run_dir():
    factory = _factory()
    storage = _storage()
    storage.write_bytes("runs/r1/plan.md", b"data")
    assert storage.exists("runs/r1/plan.md")
    acts = RunActivities(factory, FakeAgentRuntime(), storage, FakeGit(), FakeGitForge())
    acts.cleanup_workspace({"run_id": "r1", "owner_id": "u1"})
    assert not storage.exists("runs/r1")


def test_persist_sets_branch_and_pr_url():
    factory = _factory()
    run_id = _seed_run(factory)
    acts = _acts(factory)
    acts.persist_run_state({"run_id": run_id, "owner_id": "u1",
                            "branch": "agent/x", "pr_url": "https://github.com/o/r/pull/1"})
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        run = uow.runs.get(run_id)
    assert run.branch == "agent/x"
    assert run.pr_url == "https://github.com/o/r/pull/1"


def test_provision_calls_git_prepare():
    factory = _factory()
    run_id = _seed_run(factory)
    git = FakeGit()
    acts = _acts(factory, git=git)
    acts.provision_workspace({"run_id": run_id, "owner_id": "u1", "profile": "local",
                              "repo_ref": "/repo", "branch": "agent/t1"})
    assert git.prepared and git.prepared[0][2] == "agent/t1"


def test_open_pr_remote_pushes_and_records_pr_url():
    factory = _factory()
    run_id = _seed_run(factory)
    git, forge = FakeGit(has_changes=True), FakeGitForge()
    acts = _acts(factory, git=git, forge=forge)
    out = acts.open_pr({"run_id": run_id, "owner_id": "u1", "profile": "remote",
                        "branch": "agent/t1", "base": "main",
                        "title": "t", "body": "b"})
    assert out["pr_url"] == "https://github.com/fake/fake/pull/1"
    assert git.pushed and forge.opened
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        run = uow.runs.get(run_id)
    assert run.pr_url == "https://github.com/fake/fake/pull/1"


def test_open_pr_local_records_branch_only():
    factory = _factory()
    run_id = _seed_run(factory)
    git, forge = FakeGit(has_changes=True), FakeGitForge()
    acts = _acts(factory, git=git, forge=forge)
    out = acts.open_pr({"run_id": run_id, "owner_id": "u1", "profile": "local",
                        "branch": "agent/t1", "base": "main", "title": "t", "body": "b"})
    assert out["pr_url"] is None
    assert not git.pushed and not forge.opened
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        run = uow.runs.get(run_id)
    assert run.branch == "agent/t1"


def test_provision_engineer_workspace_branches_off_task():
    factory = _factory()
    run_id = _seed_run(factory)
    git = FakeGit()
    acts = _acts(factory, git=git)
    acts.provision_engineer_workspace({
        "run_id": run_id, "owner_id": "u1", "profile": "local",
        "repo_ref": "/repo", "base": "agent/task1",
        "branch": "agent/task1__backend-1-0", "workspace_key": f"runs/{run_id}/w/backend-1-0",
    })
    repo_ref, ws, branch, mode, base = git.prepared[0]
    assert branch == "agent/task1__backend-1-0" and base == "agent/task1" and mode == "worktree"
    assert ws.endswith(f"runs/{run_id}/w/backend-1-0")
