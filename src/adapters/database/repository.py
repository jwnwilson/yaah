from typing import Any, Callable, ClassVar, Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy import Select, asc, desc, func, select
from sqlalchemy.exc import IntegrityError as SQLIntegrityError
from sqlalchemy.orm import Session

from adapters.database.orm import Base
from domain.errors import IntegrityConflict, InvalidFilter, RecordNotFound
from domain.ports import PaginatedResult

DTO = TypeVar("DTO", bound=BaseModel)

_OPS: dict[str, Callable[[Any, Any], Any]] = {
    "eq": lambda col, v: col == v,
    "ne": lambda col, v: col != v,
    "in": lambda col, v: col.in_(v),
    "like": lambda col, v: col.ilike(f"%{v}%"),
    "isnull": lambda col, v: col.is_(None) if v else col.isnot(None),
    "gt": lambda col, v: col > v,
    "gte": lambda col, v: col >= v,
    "lt": lambda col, v: col < v,
    "lte": lambda col, v: col <= v,
}


class SqlRepository(Generic[DTO]):
    """Generic CRUD over one ORM row class, returning domain DTOs.

    Subclasses set `orm_model` and `dto`. `required_filters` (e.g. owner_id)
    are applied to every query, so cross-tenant rows are invisible.
    """

    orm_model: ClassVar[type[Base]]
    dto: type[DTO]
    default_order_by: ClassVar[str] = "-created_at"

    def __init__(self, session: Session, required_filters: dict[str, Any] | None = None):
        self._session = session
        self._required_filters = required_filters or {}

    def _column(self, name: str) -> Any:
        col = getattr(self.orm_model, name, None)
        if col is None:
            raise InvalidFilter(f"unknown field: {name}")
        return col

    def _scoped(self) -> Select[Any]:
        query = select(self.orm_model)
        for key, value in self._required_filters.items():
            if hasattr(self.orm_model, key):
                query = query.where(getattr(self.orm_model, key) == value)
        return query

    def _filtered(self, query: Select[Any], filters: dict[str, Any]) -> Select[Any]:
        for key, value in filters.items():
            field, _, op = key.rpartition("__")
            if not field or op not in _OPS:
                field, op = key, "eq"
            query = query.where(_OPS[op](self._column(field), value))
        return query

    def _ordered(self, query: Select[Any], order_by: str) -> Select[Any]:
        direction = desc if order_by.startswith("-") else asc
        return query.order_by(direction(self._column(order_by.lstrip("-"))))

    def _row(self, entity_id: str) -> Any:
        row = self._session.execute(
            self._scoped().where(self.orm_model.id == entity_id)
        ).scalar_one_or_none()
        if row is None:
            raise RecordNotFound(f"{self.dto.__name__} {entity_id} not found")
        return row

    def _to_dto(self, row: Any) -> DTO:
        return self.dto(**{k: v for k, v in row.__dict__.items() if not k.startswith("_")})

    def create(self, obj: DTO) -> DTO:
        row = self.orm_model(**obj.model_dump())
        try:
            self._session.add(row)
            self._session.flush()
        except SQLIntegrityError as err:
            raise IntegrityConflict(str(err.orig)) from err
        return self._to_dto(row)

    def get(self, entity_id: str) -> DTO:
        return self._to_dto(self._row(entity_id))

    def list(
        self,
        filters: dict[str, Any] | None = None,
        page_size: int = 50,
        page_number: int = 1,
        order_by: str | None = None,
    ) -> PaginatedResult[DTO]:
        query = self._filtered(self._scoped(), filters or {})
        total = int(self._session.scalar(select(func.count()).select_from(query.subquery())))
        query = self._ordered(query, order_by or self.default_order_by)
        query = query.limit(page_size).offset((page_number - 1) * page_size)
        rows = self._session.execute(query).scalars().all()
        return PaginatedResult[self.dto](  # type: ignore[misc]
            results=[self._to_dto(r) for r in rows],
            total=total,
            page_size=page_size,
            page_number=page_number,
        )

    def update(self, entity_id: str, obj: DTO) -> DTO:
        row = self._row(entity_id)
        for key, value in obj.model_dump(exclude={"id", "owner_id", "created_at"}).items():
            setattr(row, key, value)
        try:
            self._session.flush()
        except SQLIntegrityError as err:
            raise IntegrityConflict(str(err.orig)) from err
        return self._to_dto(row)

    def delete(self, entity_id: str) -> None:
        self._session.delete(self._row(entity_id))
        self._session.flush()

    def delete_many(self, filters: dict[str, Any]) -> int:
        rows = self._session.execute(self._filtered(self._scoped(), filters)).scalars().all()
        for row in rows:
            self._session.delete(row)
        self._session.flush()
        return len(rows)
