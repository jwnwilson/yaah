"""Pure run-scheduling policy. No I/O."""


def plan_starts(ready_task_ids: list[str], in_flight: int, limit: int) -> list[str]:
    """The prefix of READY task ids that fit the free concurrency slots.

    free = max(0, limit - in_flight); returns ready_task_ids[:free].
    """
    free = max(0, limit - in_flight)
    return ready_task_ids[:free]


def order_ready_tasks(ready_tasks, epics, features) -> list[str]:
    """Flatten READY tasks into the queue order that matches the backlog's visual order:
    epics by position, then within each epic its direct tasks, then each feature (by position)
    with its tasks (by position). `created_at` breaks ties. Returns task ids."""
    epic_pos = {e.id: e.position for e in epics}
    feat = {f.id: (f.parent_id, f.position) for f in features}

    def sort_key(task):
        if task.parent_id in epic_pos:
            return (epic_pos[task.parent_id], -1, task.position, task.created_at)
        parent_epic, feature_pos = feat.get(task.parent_id, (None, 0))
        return (epic_pos.get(parent_epic, 0), feature_pos, task.position, task.created_at)

    return [t.id for t in sorted(ready_tasks, key=sort_key)]
