from contextlib import AbstractContextManager
from typing import Any, Generic, Protocol, TypeVar

from pydantic import BaseModel

from domain.models import (
    AgentDefinition,
    AuditEvent,
    ChatMessage,
    ChatSession,
    McpServer,
    Notification,
    Project,
    Run,
    RunEvent,
    Secret,
    Skill,
    Team,
    UsageRecord,
    WorkItem,
)

DTO = TypeVar("DTO", bound=BaseModel)


class PaginatedResult(BaseModel, Generic[DTO]):
    results: list[DTO]
    total: int
    page_size: int
    page_number: int


class Repository(Protocol[DTO]):
    def create(self, obj: DTO) -> DTO: ...
    def get(self, entity_id: str) -> DTO: ...
    def list(
        self,
        filters: dict[str, Any] | None = None,
        page_size: int = 50,
        page_number: int = 1,
        order_by: str | None = None,
    ) -> PaginatedResult[DTO]: ...
    def update(self, entity_id: str, obj: DTO) -> DTO: ...
    def delete(self, entity_id: str) -> None: ...
    def delete_many(self, filters: dict[str, Any]) -> int: ...


class UnitOfWork(Protocol):
    def transaction(self) -> AbstractContextManager["UnitOfWork"]: ...

    @property
    def projects(self) -> Repository[Project]: ...
    @property
    def work_items(self) -> Repository[WorkItem]: ...
    @property
    def teams(self) -> Repository[Team]: ...
    @property
    def agents(self) -> Repository[AgentDefinition]: ...
    @property
    def runs(self) -> Repository[Run]: ...
    @property
    def run_events(self) -> Repository[RunEvent]: ...
    @property
    def audit_events(self) -> Repository[AuditEvent]: ...
    @property
    def skills(self) -> Repository[Skill]: ...
    @property
    def mcp_servers(self) -> Repository[McpServer]: ...
    @property
    def secrets(self) -> Repository[Secret]: ...
    @property
    def notifications(self) -> Repository[Notification]: ...
    @property
    def usage(self) -> Repository[UsageRecord]: ...
    @property
    def chat_sessions(self) -> Repository[ChatSession]: ...
    @property
    def chat_messages(self) -> Repository[ChatMessage]: ...
