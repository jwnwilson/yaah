"""Seed the local database with the startup data needed to use the board.

Idempotent: running it repeatedly will not create duplicates. It creates, for the
local dev user (`dev-user`):

  * the default team (lead + engineer + QA agent definitions)
  * a sample project wired to that team, pointing at a local git repo
  * an epic -> feature -> task hierarchy, with the task left in `ready` state so a
    run can be started against it immediately.

Run via ``make seed`` (which also provisions the sample git repo), or directly:

    PYTHONPATH=src uv run python -m interactors.cli.seed

The sample repo path is taken from ``YAAH_SEED_REPO`` (default ``/tmp/yaah-dummy``).
"""

from __future__ import annotations

import os

from adapters.database.engine import make_engine, make_session_factory
from adapters.database.ports import UnitOfWork
from adapters.database.uow import SqlUnitOfWork
from domain.models import (
    AutonomyLevel,
    Project,
    WorkItem,
    WorkItemKind,
    WorkItemStatus,
)
from domain.teams import default_team
from interactors.api.auth import DEV_USER_ID
from interactors.api.settings import Settings

DEFAULT_SEED_REPO = "/tmp/yaah-dummy"
SAMPLE_PROJECT_NAME = "Sample Project"


def _ensure_team(uow: UnitOfWork) -> str:
    """Create the default team + agents if none exists; return the team id."""
    existing = uow.teams.list().results
    if existing:
        return existing[0].id
    team, agents = default_team(owner_id=DEV_USER_ID)
    uow.teams.create(team)
    for agent in agents:
        uow.agents.create(agent)
    return team.id


def _ensure_project(uow: UnitOfWork, team_id: str, repo_path: str) -> Project:
    """Create the sample project (wired to the team) if it does not exist."""
    for project in uow.projects.list().results:
        if project.name == SAMPLE_PROJECT_NAME:
            return project
    return uow.projects.create(
        Project(
            owner_id=DEV_USER_ID,
            name=SAMPLE_PROJECT_NAME,
            local_path=repo_path,
            team_id=team_id,
            autonomy=AutonomyLevel.FULL_AUTO,
        )
    )


def _ensure_sample_work_items(uow: UnitOfWork, project_id: str) -> None:
    """Create an epic -> feature -> task chain with a ready task, if absent."""
    existing = uow.work_items.list(filters={"project_id": project_id}).results
    if existing:
        return
    epic = uow.work_items.create(
        WorkItem(
            owner_id=DEV_USER_ID,
            project_id=project_id,
            kind=WorkItemKind.EPIC,
            title="Getting started",
        )
    )
    feature = uow.work_items.create(
        WorkItem(
            owner_id=DEV_USER_ID,
            project_id=project_id,
            kind=WorkItemKind.FEATURE,
            parent_id=epic.id,
            title="Say hello",
        )
    )
    uow.work_items.create(
        WorkItem(
            owner_id=DEV_USER_ID,
            project_id=project_id,
            kind=WorkItemKind.TASK,
            parent_id=feature.id,
            title="Add hello.txt containing the word hello",
            acceptance_criteria=[
                "hello.txt exists at the repo root",
                "hello.txt contains the text hello",
            ],
            status=WorkItemStatus.READY,
        )
    )


def seed(uow: UnitOfWork, repo_path: str) -> None:
    """Populate startup data in one transaction (idempotent)."""
    with uow.transaction():
        team_id = _ensure_team(uow)
        project = _ensure_project(uow, team_id, repo_path)
        _ensure_sample_work_items(uow, project.id)
    print(f">> seeded team + '{SAMPLE_PROJECT_NAME}' (repo: {repo_path})")


def main() -> None:
    settings = Settings()
    repo_path = os.environ.get("YAAH_SEED_REPO", DEFAULT_SEED_REPO)
    session_factory = make_session_factory(make_engine(settings.database_url))
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": DEV_USER_ID})
    seed(uow, repo_path)


if __name__ == "__main__":
    main()
