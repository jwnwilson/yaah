from __future__ import annotations

from sqlalchemy import delete, insert, select, update
from sqlalchemy.orm import Session, sessionmaker

from adapters.database import tables
from domain.models import (
    AgentDefinition,
    Project,
    Run,
    Team,
    WorkItem,
    WorkItemKind,
    WorkItemStatus,
)


class SqlProjectStore:
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sf = session_factory

    def add(self, project: Project) -> Project:
        with self._sf() as s, s.begin():
            s.execute(insert(tables.projects).values(**project.model_dump()))
        return project

    def get(self, project_id: str, owner_id: str) -> Project | None:
        with self._sf() as s:
            row = (
                s.execute(
                    select(tables.projects).where(
                        tables.projects.c.id == project_id, tables.projects.c.owner_id == owner_id
                    )
                )
                .mappings()
                .first()
            )
        return Project(**row) if row else None

    def list(self, owner_id: str, limit: int = 50, offset: int = 0) -> list[Project]:
        with self._sf() as s:
            rows = (
                s.execute(
                    select(tables.projects)
                    .where(tables.projects.c.owner_id == owner_id)
                    .order_by(tables.projects.c.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
                .mappings()
                .all()
            )
        return [Project(**r) for r in rows]

    def update(self, project: Project) -> Project:
        with self._sf() as s, s.begin():
            s.execute(
                update(tables.projects)
                .where(tables.projects.c.id == project.id)
                .values(**project.model_dump())
            )
        return project

    def delete(self, project_id: str, owner_id: str) -> bool:
        with self._sf() as s, s.begin():
            result = s.execute(
                delete(tables.projects).where(
                    tables.projects.c.id == project_id, tables.projects.c.owner_id == owner_id
                )
            )
        return result.rowcount > 0


class SqlWorkItemStore:
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sf = session_factory

    def add(self, item: WorkItem) -> WorkItem:
        with self._sf() as s, s.begin():
            s.execute(insert(tables.work_items).values(**item.model_dump()))
        return item

    def get(self, item_id: str) -> WorkItem | None:
        with self._sf() as s:
            row = (
                s.execute(select(tables.work_items).where(tables.work_items.c.id == item_id))
                .mappings()
                .first()
            )
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
        stmt = select(tables.work_items).where(tables.work_items.c.project_id == project_id)
        if kind:
            stmt = stmt.where(tables.work_items.c.kind == kind)
        if status:
            stmt = stmt.where(tables.work_items.c.status == status)
        if parent_id:
            stmt = stmt.where(tables.work_items.c.parent_id == parent_id)
        stmt = stmt.order_by(tables.work_items.c.created_at).limit(limit).offset(offset)
        with self._sf() as s:
            rows = s.execute(stmt).mappings().all()
        return [WorkItem(**r) for r in rows]

    def update(self, item: WorkItem) -> WorkItem:
        with self._sf() as s, s.begin():
            s.execute(
                update(tables.work_items)
                .where(tables.work_items.c.id == item.id)
                .values(**item.model_dump())
            )
        return item

    def delete(self, item_id: str) -> bool:
        with self._sf() as s, s.begin():
            result = s.execute(delete(tables.work_items).where(tables.work_items.c.id == item_id))
        return result.rowcount > 0


class SqlTeamStore:
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sf = session_factory

    def add(self, team: Team, agents: list[AgentDefinition]) -> Team:
        with self._sf() as s, s.begin():
            s.execute(insert(tables.teams).values(**team.model_dump()))
            for agent in agents:
                s.execute(insert(tables.agent_definitions).values(**agent.model_dump()))
        return team

    def get(self, team_id: str, owner_id: str) -> Team | None:
        with self._sf() as s:
            row = (
                s.execute(
                    select(tables.teams).where(
                        tables.teams.c.id == team_id, tables.teams.c.owner_id == owner_id
                    )
                )
                .mappings()
                .first()
            )
        return Team(**row) if row else None

    def list(self, owner_id: str) -> list[Team]:
        with self._sf() as s:
            rows = (
                s.execute(select(tables.teams).where(tables.teams.c.owner_id == owner_id))
                .mappings()
                .all()
            )
        return [Team(**r) for r in rows]

    def agents(self, team_id: str) -> list[AgentDefinition]:
        with self._sf() as s:
            rows = (
                s.execute(
                    select(tables.agent_definitions).where(
                        tables.agent_definitions.c.team_id == team_id
                    )
                )
                .mappings()
                .all()
            )
        return [AgentDefinition(**r) for r in rows]


class SqlRunStore:
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sf = session_factory

    def add(self, run: Run) -> Run:
        with self._sf() as s, s.begin():
            s.execute(insert(tables.runs).values(**run.model_dump()))
        return run

    def get(self, run_id: str) -> Run | None:
        with self._sf() as s:
            row = (
                s.execute(select(tables.runs).where(tables.runs.c.id == run_id)).mappings().first()
            )
        return Run(**row) if row else None

    def list_for_task(self, task_id: str) -> list[Run]:
        with self._sf() as s:
            rows = (
                s.execute(
                    select(tables.runs)
                    .where(tables.runs.c.task_id == task_id)
                    .order_by(tables.runs.c.created_at.desc())
                )
                .mappings()
                .all()
            )
        return [Run(**r) for r in rows]

    def update(self, run: Run) -> Run:
        with self._sf() as s, s.begin():
            s.execute(
                update(tables.runs).where(tables.runs.c.id == run.id).values(**run.model_dump())
            )
        return run
