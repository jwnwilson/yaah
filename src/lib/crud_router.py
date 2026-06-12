import json
from typing import Any, Callable

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from domain.errors import InvalidFilter
from domain.models import utc_now
from domain.ports import UnitOfWork
from interactors.api.auth import current_user_id
from interactors.api.deps import get_uow
from interactors.api.envelope import ok


class CrudRouter(APIRouter):
    """Envelope-aware port of hexrepo's CrudRouter (see docs/architecture.md).

    Generates standard CRUD routes backed by a UnitOfWork repository. Custom
    routes override generated ones via the decorator methods below, which
    remove the colliding generated route first.
    """

    def __init__(
        self,
        *,
        repository: str,
        response_dto: type[BaseModel],
        create_schema: type[BaseModel] | None = None,
        update_schema: type[BaseModel] | None = None,
        methods: tuple[str, ...] = ("READ",),
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.repository = repository
        self.response_dto = response_dto
        self.create_schema = create_schema
        self.update_schema = update_schema
        self._setup(methods)

    def _setup(self, methods: tuple[str, ...]) -> None:
        if "CREATE" in methods:
            self.add_api_route("", self._create(), methods=["POST"], status_code=201)
        if "READ" in methods:
            self.add_api_route("", self._list(), methods=["GET"])
            self.add_api_route("/{entity_id}", self._read(), methods=["GET"])
        if "UPDATE" in methods:
            self.add_api_route("/{entity_id}", self._update(), methods=["PATCH"])
        if "DELETE" in methods:
            self.add_api_route("/{entity_id}", self._delete(), methods=["DELETE"])

    def _create(self) -> Callable[..., dict]:
        create_schema, dto, repo_name = self.create_schema, self.response_dto, self.repository

        def handler(
            body: create_schema,  # type: ignore[valid-type]
            user_id: str = Depends(current_user_id),
            uow: UnitOfWork = Depends(get_uow),
        ) -> dict:
            obj = dto(owner_id=user_id, **body.model_dump())
            with uow.transaction():
                created = getattr(uow, repo_name).create(obj)
            return ok(created.model_dump(mode="json"))

        return handler

    def _read(self) -> Callable[..., dict]:
        repo_name = self.repository

        def handler(entity_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
            with uow.transaction():
                obj = getattr(uow, repo_name).get(entity_id)
            return ok(obj.model_dump(mode="json"))

        return handler

    def _list(self) -> Callable[..., dict]:
        repo_name = self.repository

        def handler(
            filters: str = "{}",
            page_size: int = Query(50, ge=1, le=200),
            page_number: int = Query(1, ge=1),
            order_by: str = "-created_at",
            uow: UnitOfWork = Depends(get_uow),
        ) -> dict:
            try:
                parsed: dict[str, Any] = json.loads(filters)
            except json.JSONDecodeError as exc:
                raise InvalidFilter(f"filters must be a JSON object: {exc}") from exc
            if not isinstance(parsed, dict):
                raise InvalidFilter("filters must be a JSON object")
            with uow.transaction():
                page = getattr(uow, repo_name).list(
                    filters=parsed,
                    page_size=page_size,
                    page_number=page_number,
                    order_by=order_by,
                )
            return ok(
                [r.model_dump(mode="json") for r in page.results],
                meta={
                    "total": page.total,
                    "page_size": page.page_size,
                    "page_number": page.page_number,
                },
            )

        return handler

    def _update(self) -> Callable[..., dict]:
        update_schema, repo_name = self.update_schema, self.repository

        def handler(
            entity_id: str,
            body: update_schema,  # type: ignore[valid-type]
            uow: UnitOfWork = Depends(get_uow),
        ) -> dict:
            with uow.transaction():
                repo = getattr(uow, repo_name)
                current = repo.get(entity_id)
                changes = body.model_dump(exclude_none=True)
                if "updated_at" in type(current).model_fields:
                    changes["updated_at"] = utc_now()
                updated = repo.update(entity_id, current.model_copy(update=changes))
            return ok(updated.model_dump(mode="json"))

        return handler

    def _delete(self) -> Callable[..., dict]:
        repo_name = self.repository

        def handler(entity_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
            with uow.transaction():
                getattr(uow, repo_name).delete(entity_id)
            return ok({"deleted": entity_id})

        return handler

    def _remove_route(self, path: str, methods: list[str]) -> None:
        wanted = set(methods)
        for route in list(self.routes):
            if route.path == f"{self.prefix}{path}" and route.methods == wanted:  # type: ignore[attr-defined]
                self.routes.remove(route)

    def get(self, path: str, *args: Any, **kwargs: Any) -> Callable:  # type: ignore[override]
        self._remove_route(path, ["GET"])
        return super().get(path, *args, **kwargs)

    def post(self, path: str, *args: Any, **kwargs: Any) -> Callable:  # type: ignore[override]
        self._remove_route(path, ["POST"])
        return super().post(path, *args, **kwargs)

    def patch(self, path: str, *args: Any, **kwargs: Any) -> Callable:  # type: ignore[override]
        self._remove_route(path, ["PATCH"])
        return super().patch(path, *args, **kwargs)

    def delete(self, path: str, *args: Any, **kwargs: Any) -> Callable:  # type: ignore[override]
        self._remove_route(path, ["DELETE"])
        return super().delete(path, *args, **kwargs)
