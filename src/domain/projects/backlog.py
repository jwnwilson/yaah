"""Pure backlog read-model: per-epic readiness counts + project scheduling summary. No I/O."""
from collections import defaultdict

from pydantic import BaseModel

from domain.projects.work_items import WorkItem, WorkItemStatus


class BacklogEpic(BaseModel):
    epic: WorkItem
    active: bool
    ready_count: int
    total_tasks: int
    done: int
    in_flight_count: int


class BacklogView(BaseModel):
    epics: list[BacklogEpic]
    max_concurrent_runs: int
    in_flight: int
    queued: int


def build_backlog(
    *,
    epics: list[WorkItem],
    features: list[WorkItem],
    tasks: list[WorkItem],
    in_flight_task_ids: set[str],
    max_concurrent_runs: int,
) -> BacklogView:
    features_by_epic: dict[str, list[WorkItem]] = defaultdict(list)
    for f in features:
        features_by_epic[f.parent_id].append(f)

    backlog_epics: list[BacklogEpic] = []
    total_in_flight = 0
    total_queued = 0
    for epic in epics:
        owned = {epic.id, *(f.id for f in features_by_epic.get(epic.id, []))}
        epic_tasks = [t for t in tasks if t.parent_id in owned]
        ready = sum(1 for t in epic_tasks if t.status == WorkItemStatus.READY)
        done = sum(1 for t in epic_tasks if t.status == WorkItemStatus.DONE)
        in_flight = sum(1 for t in epic_tasks if t.id in in_flight_task_ids)
        backlog_epics.append(BacklogEpic(
            epic=epic, active=epic.active, ready_count=ready,
            total_tasks=len(epic_tasks), done=done, in_flight_count=in_flight,
        ))
        total_in_flight += in_flight
        if epic.active:
            total_queued += ready
    return BacklogView(
        epics=backlog_epics, max_concurrent_runs=max_concurrent_runs,
        in_flight=total_in_flight, queued=total_queued,
    )
