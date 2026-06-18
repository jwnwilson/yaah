"""Pure run-scheduling policy. No I/O."""


def plan_starts(ready_task_ids: list[str], in_flight: int, limit: int) -> list[str]:
    """The prefix of READY task ids that fit the free concurrency slots.

    free = max(0, limit - in_flight); returns ready_task_ids[:free].
    """
    free = max(0, limit - in_flight)
    return ready_task_ids[:free]
