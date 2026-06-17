"""Task-management domain: the project → epic → feature/task hierarchy.

Re-exports the project, work-item, and epic-board entities so callers import from
``domain.projects``. The package only depends on ``domain.base`` — no cycles.
"""
from domain.projects.epics import EpicBoard, FeatureProgress, build_epic_board
from domain.projects.projects import AutonomyLevel, Project
from domain.projects.work_items import WorkItem, WorkItemKind, WorkItemStatus

__all__ = [
    "AutonomyLevel",
    "EpicBoard",
    "FeatureProgress",
    "Project",
    "WorkItem",
    "WorkItemKind",
    "WorkItemStatus",
    "build_epic_board",
]
