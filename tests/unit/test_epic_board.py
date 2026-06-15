"""Unit tests for the pure epic-board read-model."""
from domain.epics import build_epic_board
from domain.models import WorkItem, WorkItemKind, WorkItemStatus


def _epic() -> WorkItem:
    return WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.EPIC, title="E")


def _feature(epic_id: str, title: str) -> WorkItem:
    return WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.FEATURE,
                    parent_id=epic_id, title=title)


def _task(parent_id: str, status: WorkItemStatus = WorkItemStatus.DRAFT) -> WorkItem:
    return WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.TASK,
                    parent_id=parent_id, title="t", status=status)


def test_groups_tasks_under_features_with_done_counts():
    epic = _epic()
    f1 = _feature(epic.id, "Cart")
    tasks = [_task(f1.id, WorkItemStatus.DONE), _task(f1.id)]
    board = build_epic_board(epic, [f1], tasks)
    assert board.epic.id == epic.id
    assert board.features[0].feature.id == f1.id
    assert board.features[0].total == 2
    assert board.features[0].done == 1


def test_total_counts_include_tasks_parented_directly_to_epic():
    epic = _epic()
    f1 = _feature(epic.id, "Cart")
    tasks = [_task(f1.id, WorkItemStatus.DONE), _task(epic.id, WorkItemStatus.DONE)]
    board = build_epic_board(epic, [f1], tasks)
    assert board.total == 2
    assert board.done == 2
    # direct-to-epic task is not counted under any feature
    assert board.features[0].total == 1


def test_empty_epic_has_zero_counts_and_no_features():
    epic = _epic()
    board = build_epic_board(epic, [], [])
    assert board.features == []
    assert board.total == 0 and board.done == 0
