from domain.projects import WorkItem, WorkItemKind, WorkItemStatus
from domain.projects.scheduling import order_ready_tasks, plan_starts


def _wi(kind, *, id_, parent=None, position=0):
    status = WorkItemStatus.READY if kind == WorkItemKind.TASK else WorkItemStatus.DRAFT
    return WorkItem(id=id_, owner_id="o", project_id="p", kind=kind, parent_id=parent,
                    title=id_, position=position, status=status)


def test_order_ready_tasks_follows_hierarchical_position():
    e1 = _wi(WorkItemKind.EPIC, id_="e1", position=0)
    e2 = _wi(WorkItemKind.EPIC, id_="e2", position=1)
    f1 = _wi(WorkItemKind.FEATURE, id_="f1", parent="e1", position=0)
    f2 = _wi(WorkItemKind.FEATURE, id_="f2", parent="e1", position=1)
    tasks = [
        _wi(WorkItemKind.TASK, id_="t_f2", parent="f2", position=0),
        _wi(WorkItemKind.TASK, id_="t_f1b", parent="f1", position=1),
        _wi(WorkItemKind.TASK, id_="t_f1a", parent="f1", position=0),
        _wi(WorkItemKind.TASK, id_="t_e2", parent="e2", position=0),
    ]
    order = order_ready_tasks(tasks, [e1, e2], [f1, f2])
    # epic e1 (f1 tasks by position, then f2), then epic e2's task
    assert order == ["t_f1a", "t_f1b", "t_f2", "t_e2"]


def test_plan_starts_fills_free_slots_in_order():
    assert plan_starts(["a", "b", "c"], in_flight=1, limit=2) == ["a"]


def test_plan_starts_returns_all_when_room():
    assert plan_starts(["a", "b"], in_flight=0, limit=5) == ["a", "b"]


def test_plan_starts_empty_when_full():
    assert plan_starts(["a", "b"], in_flight=2, limit=2) == []


def test_plan_starts_empty_when_over_capacity():
    assert plan_starts(["a"], in_flight=3, limit=2) == []


def test_plan_starts_empty_queue():
    assert plan_starts([], in_flight=0, limit=2) == []
