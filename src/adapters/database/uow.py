import contextlib
from typing import Any, Iterator

from sqlalchemy.orm import Session, sessionmaker

from adapters.database.repositories import (
    AgentDefinitionRepository,
    AuditEventRepository,
    ChatMessageRepository,
    ChatSessionRepository,
    McpServerRepository,
    MemoryProposalRepository,
    NotificationRepository,
    ProjectRepository,
    RunEventRepository,
    RunRepository,
    SecretRepository,
    SkillRepository,
    TeamRepository,
    UsageRecordRepository,
    WorkItemRepository,
)


class SqlUnitOfWork:
    """One session/transaction shared by all repositories. The app factory owns
    the engine/session_factory; one UoW is built per request with the caller's
    required filters (owner scoping)."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        required_filters: dict[str, Any] | None = None,
    ):
        self._session_factory = session_factory
        self._required_filters = required_filters or {}
        self._session: Session | None = None

    @contextlib.contextmanager
    def transaction(self) -> Iterator["SqlUnitOfWork"]:
        if self._session is not None:
            raise RuntimeError("transaction already in progress")
        self._session = self._session_factory()
        try:
            yield self
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        finally:
            self._session.close()
            self._session = None

    @property
    def session(self) -> Session:
        if self._session is None:
            raise RuntimeError("no active transaction")
        return self._session

    @property
    def projects(self) -> ProjectRepository:
        return ProjectRepository(self.session, self._required_filters)

    @property
    def work_items(self) -> WorkItemRepository:
        return WorkItemRepository(self.session, self._required_filters)

    @property
    def teams(self) -> TeamRepository:
        return TeamRepository(self.session, self._required_filters)

    @property
    def agents(self) -> AgentDefinitionRepository:
        return AgentDefinitionRepository(self.session, self._required_filters)

    @property
    def runs(self) -> RunRepository:
        return RunRepository(self.session, self._required_filters)

    @property
    def run_events(self) -> RunEventRepository:
        return RunEventRepository(self.session, self._required_filters)

    @property
    def audit_events(self) -> AuditEventRepository:
        return AuditEventRepository(self.session, self._required_filters)

    @property
    def skills(self) -> SkillRepository:
        return SkillRepository(self.session, self._required_filters)

    @property
    def mcp_servers(self) -> McpServerRepository:
        return McpServerRepository(self.session, self._required_filters)

    @property
    def secrets(self) -> SecretRepository:
        return SecretRepository(self.session, self._required_filters)

    @property
    def notifications(self) -> NotificationRepository:
        return NotificationRepository(self.session, self._required_filters)

    @property
    def usage(self) -> UsageRecordRepository:
        return UsageRecordRepository(self.session, self._required_filters)

    @property
    def chat_sessions(self) -> ChatSessionRepository:
        return ChatSessionRepository(self.session, self._required_filters)

    @property
    def chat_messages(self) -> ChatMessageRepository:
        return ChatMessageRepository(self.session, self._required_filters)

    @property
    def memory_proposals(self) -> MemoryProposalRepository:
        return MemoryProposalRepository(self.session, self._required_filters)
