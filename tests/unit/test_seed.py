from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.models import WorkItemKind, WorkItemStatus
from interactors.api.auth import DEV_USER_ID
from interactors.cli.seed import SAMPLE_PROJECT_NAME, seed

_REPO = "/tmp/seed-test-repo"


def _uow() -> SqlUnitOfWork:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return SqlUnitOfWork(make_session_factory(engine), required_filters={"owner_id": DEV_USER_ID})


def test_seed_creates_team_project_and_ready_task():
    # Arrange
    uow = _uow()

    # Act
    seed(uow, _REPO)

    # Assert
    with uow.transaction():
        teams = uow.teams.list().results
        assert len(teams) == 1
        projects = uow.projects.list().results
        assert [p.name for p in projects] == [SAMPLE_PROJECT_NAME]
        assert projects[0].local_path == _REPO
        assert projects[0].team_id == teams[0].id

        items = uow.work_items.list(filters={"project_id": projects[0].id}).results
        kinds = sorted(i.kind for i in items)
        assert kinds == [WorkItemKind.EPIC, WorkItemKind.FEATURE, WorkItemKind.TASK]
        task = next(i for i in items if i.kind == WorkItemKind.TASK)
        assert task.status == WorkItemStatus.READY
        assert task.acceptance_criteria  # criteria were seeded


def test_seed_is_idempotent():
    # Arrange
    uow = _uow()
    seed(uow, _REPO)

    # Act — running again must not duplicate anything
    seed(uow, _REPO)

    # Assert
    with uow.transaction():
        assert uow.teams.list().total == 1
        assert uow.projects.list().total == 1
        project_id = uow.projects.list().results[0].id
        assert uow.work_items.list(filters={"project_id": project_id}).total == 3
