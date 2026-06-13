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


def test_capability_repos_owner_scoped_and_agent_grants():
    from adapters.database.engine import make_engine, make_session_factory
    from adapters.database.orm import Base
    from adapters.database.uow import SqlUnitOfWork
    from domain.models import AgentDefinition, Skill, Team

    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        sk = uow.skills.create(Skill(owner_id="u1", name="pytest"))
        team = uow.teams.create(Team(owner_id="u1", name="T"))
        uow.agents.create(AgentDefinition(team_id=team.id, role="lead", name="L",
                                          model_alias="m", skill_ids=[sk.id]))
        skills_page = uow.skills.list()
        agent = uow.agents.list(filters={"team_id": team.id}).results[0]
    assert skills_page.total == 1 and agent.skill_ids == [sk.id]

    other = SqlUnitOfWork(factory, required_filters={"owner_id": "u2"})
    with other.transaction():
        assert other.skills.list().total == 0   # cross-tenant hidden


def test_audit_events_owner_scoped():
    from adapters.database.engine import make_engine, make_session_factory
    from adapters.database.orm import Base
    from adapters.database.uow import SqlUnitOfWork
    from domain.models import AuditAction, AuditEvent, RunStage

    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        uow.audit_events.create(AuditEvent(run_id="r1", owner_id="u1", stage=RunStage.PLAN,
                                           actor="lead", action=AuditAction.CAPABILITY_GRANTED,
                                           detail={"tools": ["Read"]}))
        page = uow.audit_events.list(filters={"run_id": "r1"})
    assert page.total == 1 and page.results[0].detail["tools"] == ["Read"]
    other = SqlUnitOfWork(factory, required_filters={"owner_id": "u2"})
    with other.transaction():
        assert other.audit_events.list(filters={"run_id": "r1"}).total == 0


def test_secret_roundtrips_encrypted_value():
    from adapters.database.engine import make_engine, make_session_factory
    from adapters.database.orm import Base
    from adapters.database.uow import SqlUnitOfWork
    from domain.models import Secret

    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    uow = SqlUnitOfWork(make_session_factory(engine), required_filters={"owner_id": "u1"})
    with uow.transaction():
        sec = uow.secrets.create(Secret(owner_id="u1", name="GH"))
        assert sec.encrypted_value is None
        stored = uow.secrets.update(sec.id, sec.model_copy(update={"encrypted_value": "tok"}))
    assert stored.encrypted_value == "tok"


def test_chat_repos_owner_scoped():
    from adapters.database.engine import make_engine, make_session_factory
    from adapters.database.orm import Base
    from adapters.database.uow import SqlUnitOfWork
    from domain.models import ChatMessage, ChatRole, ChatSession

    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        s = uow.chat_sessions.create(ChatSession(owner_id="u1", project_id="p1"))
        uow.chat_messages.create(ChatMessage(owner_id="u1", session_id=s.id,
                                             role=ChatRole.USER, content="hi"))
        msgs = uow.chat_messages.list(filters={"session_id": s.id}, order_by="created_at")
    assert msgs.total == 1 and msgs.results[0].content == "hi"
    other = SqlUnitOfWork(factory, required_filters={"owner_id": "u2"})
    with other.transaction():
        assert other.chat_sessions.list(filters={"project_id": "p1"}).total == 0
