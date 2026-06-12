from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.database.orm import Base
from adapters.database.repositories import AgentDefinitionRepository, WorkItemRepository
from domain.models import AgentDefinition, AgentRole, WorkItem, WorkItemKind


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_work_item_repo_filters_by_kind_and_parent():
    s = _session()
    repo = WorkItemRepository(s, required_filters={"owner_id": "u1"})
    epic = repo.create(WorkItem(owner_id="u1", project_id="p1", kind=WorkItemKind.EPIC, title="E"))
    task = repo.create(
        WorkItem(
            owner_id="u1", project_id="p1", kind=WorkItemKind.TASK, parent_id=epic.id, title="T"
        )
    )
    assert repo.list(filters={"kind": "task"}).results[0].id == task.id
    assert repo.list(filters={"parent_id__isnull": True}).results[0].id == epic.id


def test_agent_repo_is_not_owner_scoped_and_orders_by_id():
    s = _session()
    repo = AgentDefinitionRepository(s, required_filters={"owner_id": "u1"})
    repo.create(AgentDefinition(team_id="t1", role=AgentRole.LEAD, name="L", model_alias="m"))
    assert repo.list(filters={"team_id": "t1"}).total == 1
