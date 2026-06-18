from domain.projects import WorkItem, WorkItemKind, WorkItemStatus, build_backlog


def _epic(id_, active=False):
    return WorkItem(id=id_, owner_id="o", project_id="p", kind=WorkItemKind.EPIC,
                    title="E", active=active)


def _feature(id_, epic_id):
    return WorkItem(id=id_, owner_id="o", project_id="p", kind=WorkItemKind.FEATURE,
                    parent_id=epic_id, title="F")


def _task(parent_id, status):
    return WorkItem(owner_id="o", project_id="p", kind=WorkItemKind.TASK,
                    parent_id=parent_id, title="T", status=status)


def test_build_backlog_counts_and_summary():
    epic = _epic("e1", active=True)
    feat = _feature("f1", "e1")
    tasks = [
        _task("f1", WorkItemStatus.READY),
        _task("f1", WorkItemStatus.READY),
        _task("e1", WorkItemStatus.DONE),
        _task("f1", WorkItemStatus.IN_PROGRESS),
    ]
    in_flight_task_ids = {tasks[3].id}

    view = build_backlog(
        epics=[epic], features=[feat], tasks=tasks,
        in_flight_task_ids=in_flight_task_ids, max_concurrent_runs=2,
    )

    assert len(view.epics) == 1
    be = view.epics[0]
    assert be.active is True
    assert be.total_tasks == 4
    assert be.ready_count == 2
    assert be.done == 1
    assert be.in_flight_count == 1
    assert view.max_concurrent_runs == 2
    assert view.in_flight == 1
    assert view.queued == 2


def test_build_backlog_inactive_epic_not_queued():
    epic = _epic("e1", active=False)
    tasks = [_task("e1", WorkItemStatus.READY)]
    view = build_backlog(epics=[epic], features=[], tasks=tasks,
                         in_flight_task_ids=set(), max_concurrent_runs=2)
    assert view.epics[0].ready_count == 1
    assert view.queued == 0
