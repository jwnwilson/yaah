from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.agent.runtime.fake import FakeAgentRuntime
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from adapters.storage.local import LocalStorageAdapter
from domain.agent.teams import default_team
from domain.projects import Project, WorkItem, WorkItemKind, WorkItemStatus
from interactors.temporal.activities import RunActivities


class _Settings:
    profile = "local"
    github_base_branch = "main"


class _FakeRunClient:
    def __init__(self):
        self.started = []

    def start_run_workflow(self, run_input, workflow_name="OrchestratorWorkflow"):
        self.started.append((workflow_name, run_input))


def _factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_reconcile_activity_starts_ready_tasks(tmp_path):
    factory = _factory()
    client = _FakeRunClient()
    acts = RunActivities(
        factory, FakeAgentRuntime(storage=LocalStorageAdapter(base_dir=str(tmp_path))),
        LocalStorageAdapter(base_dir=str(tmp_path)), git=None, forge=None,
        settings=_Settings(), run_client=client,
    )
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "o"})
    team, agents = default_team("o")
    with uow.transaction():
        uow.teams.create(team)
        for a in agents:
            uow.agents.create(a)
        project = uow.projects.create(
            Project(owner_id="o", name="p", repo_url="r", team_id=team.id, max_concurrent_runs=2))
        epic = uow.work_items.create(WorkItem(
            owner_id="o", project_id=project.id, kind=WorkItemKind.EPIC, title="E", active=True))
        uow.work_items.create(WorkItem(
            owner_id="o", project_id=project.id, kind=WorkItemKind.TASK, parent_id=epic.id,
            title="T", status=WorkItemStatus.READY))

    acts.reconcile_project_runs({"owner_id": "o", "project_id": project.id})
    assert len(client.started) == 1
