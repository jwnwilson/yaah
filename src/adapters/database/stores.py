from sqlalchemy import delete, insert, select, update
from sqlalchemy.orm import Session, sessionmaker

from adapters.database.tables import projects, work_items
from domain.models import Project, WorkItem, WorkItemKind, WorkItemStatus


class SqlProjectStore:
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sf = session_factory

    def add(self, project: Project) -> Project:
        with self._sf() as s, s.begin():
            s.execute(insert(projects).values(**project.model_dump()))
        return project

    def get(self, project_id: str, owner_id: str) -> Project | None:
        with self._sf() as s:
            row = s.execute(
                select(projects).where(projects.c.id == project_id, projects.c.owner_id == owner_id)
            ).mappings().first()
        return Project(**row) if row else None

    def list(self, owner_id: str, limit: int = 50, offset: int = 0) -> list[Project]:
        with self._sf() as s:
            rows = s.execute(
                select(projects)
                .where(projects.c.owner_id == owner_id)
                .order_by(projects.c.created_at.desc())
                .limit(limit)
                .offset(offset)
            ).mappings().all()
        return [Project(**r) for r in rows]

    def update(self, project: Project) -> Project:
        with self._sf() as s, s.begin():
            s.execute(update(projects).where(projects.c.id == project.id).values(**project.model_dump()))
        return project

    def delete(self, project_id: str, owner_id: str) -> bool:
        with self._sf() as s, s.begin():
            result = s.execute(
                delete(projects).where(projects.c.id == project_id, projects.c.owner_id == owner_id)
            )
        return result.rowcount > 0


class SqlWorkItemStore:
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sf = session_factory

    def add(self, item: WorkItem) -> WorkItem:
        with self._sf() as s, s.begin():
            s.execute(insert(work_items).values(**item.model_dump()))
        return item

    def get(self, item_id: str) -> WorkItem | None:
        with self._sf() as s:
            row = s.execute(select(work_items).where(work_items.c.id == item_id)).mappings().first()
        return WorkItem(**row) if row else None

    def list(
        self,
        project_id: str,
        kind: WorkItemKind | None = None,
        status: WorkItemStatus | None = None,
        parent_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[WorkItem]:
        stmt = select(work_items).where(work_items.c.project_id == project_id)
        if kind:
            stmt = stmt.where(work_items.c.kind == kind)
        if status:
            stmt = stmt.where(work_items.c.status == status)
        if parent_id:
            stmt = stmt.where(work_items.c.parent_id == parent_id)
        stmt = stmt.order_by(work_items.c.created_at).limit(limit).offset(offset)
        with self._sf() as s:
            rows = s.execute(stmt).mappings().all()
        return [WorkItem(**r) for r in rows]

    def update(self, item: WorkItem) -> WorkItem:
        with self._sf() as s, s.begin():
            s.execute(update(work_items).where(work_items.c.id == item.id).values(**item.model_dump()))
        return item

    def delete(self, item_id: str) -> bool:
        with self._sf() as s, s.begin():
            result = s.execute(delete(work_items).where(work_items.c.id == item_id))
        return result.rowcount > 0
