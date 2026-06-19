"""Unit tests for the WorkItem domain model."""
from domain.projects import WorkItem, WorkItemKind


def test_work_item_carries_chat_session_id():
    item = WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.EPIC,
                    title="E", chat_session_id="s1")
    assert item.chat_session_id == "s1"


def test_work_item_chat_session_id_defaults_none():
    item = WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.EPIC, title="E")
    assert item.chat_session_id is None
