from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.agent.teams import default_team
from domain.projects import Project, WorkItem, WorkItemKind, WorkItemStatus
from interactors.scheduling import reconcile_project


class _Settings:
    profile = "local"
    github_base_branch = "main"


def _uow():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return SqlUnitOfWork(sessionmaker(bind=engine), required_filters={"owner_id": "o"})


def _seed_project_with_team(uow) -> Project:
    team, agents = default_team("o")
    with uow.transaction():
        uow.teams.create(team)
        for a in agents:
            uow.agents.create(a)
        return uow.projects.create(
            Project(owner_id="o", name="p", repo_url="r", team_id=team.id, max_concurrent_runs=2)
        )


def _add(uow, **kw) -> WorkItem:
    with uow.transaction():
        return uow.work_items.create(WorkItem(owner_id="o", project_id=kw.pop("project_id"), **kw))


def test_reconcile_starts_up_to_limit():
    uow = _uow()
    project = _seed_project_with_team(uow)
    epic = _add(uow, project_id=project.id, kind=WorkItemKind.EPIC, title="E", active=True)
    for i in range(3):
        _add(uow, project_id=project.id, kind=WorkItemKind.TASK, parent_id=epic.id,
             title=f"T{i}", status=WorkItemStatus.READY)

    with uow.transaction():
        run_inputs = reconcile_project(uow, _Settings(), project.id)

    assert len(run_inputs) == 2
    with uow.transaction():
        tasks = uow.work_items.list(
            filters={"project_id": project.id, "kind": WorkItemKind.TASK}, page_size=100).results
    statuses = sorted(t.status.value for t in tasks)
    assert statuses == ["in_progress", "in_progress", "ready"]


def test_reconcile_skips_inactive_epic():
    uow = _uow()
    project = _seed_project_with_team(uow)
    epic = _add(uow, project_id=project.id, kind=WorkItemKind.EPIC, title="E", active=False)
    _add(uow, project_id=project.id, kind=WorkItemKind.TASK, parent_id=epic.id,
         title="T", status=WorkItemStatus.READY)
    with uow.transaction():
        assert reconcile_project(uow, _Settings(), project.id) == []


def test_reconcile_noop_without_team():
    uow = _uow()
    with uow.transaction():
        project = uow.projects.create(Project(owner_id="o", name="p", repo_url="r"))
    with uow.transaction():
        assert reconcile_project(uow, _Settings(), project.id) == []
