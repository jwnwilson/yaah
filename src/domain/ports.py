from contextlib import AbstractContextManager
from typing import Any, Generic, Protocol, TypeVar

from pydantic import BaseModel

from domain.models import AgentDefinition, Project, Run, Team, WorkItem

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
