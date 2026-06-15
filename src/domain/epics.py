"""Pure epic-board read-model: groups an epic's features/tasks and counts progress. No I/O."""
from collections import defaultdict

from pydantic import BaseModel

from domain.models import WorkItem, WorkItemStatus


class FeatureProgress(BaseModel):
    feature: WorkItem
    total: int
    done: int


class EpicBoard(BaseModel):
    epic: WorkItem
    features: list[FeatureProgress]
    tasks: list[WorkItem]
    total: int
    done: int


def build_epic_board(
    epic: WorkItem, features: list[WorkItem], tasks: list[WorkItem]
) -> EpicBoard:
    by_parent: dict[str | None, list[WorkItem]] = defaultdict(list)
    for task in tasks:
        by_parent[task.parent_id].append(task)

    feature_progress = [
        FeatureProgress(
            feature=feature,
            total=len(by_parent.get(feature.id, [])),
            done=sum(
                1 for t in by_parent.get(feature.id, []) if t.status == WorkItemStatus.DONE
            ),
        )
        for feature in features
    ]
    return EpicBoard(
        epic=epic,
        features=feature_progress,
        tasks=tasks,
        total=len(tasks),
        done=sum(1 for t in tasks if t.status == WorkItemStatus.DONE),
    )
