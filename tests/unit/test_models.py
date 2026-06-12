import pytest
from pydantic import ValidationError

from domain.models import (
    AgentRole,
    AutonomyLevel,
    Project,
    WorkItem,
    WorkItemKind,
    WorkItemStatus,
)


def test_project_gets_id_and_defaults():
    p = Project(owner_id="dev-user", name="llm_api", repo_url="https://github.com/x/llm_api")
    assert len(p.id) == 32  # uuid hex
    assert p.autonomy == AutonomyLevel.GATED_ALL


def test_project_requires_repo_url_or_local_path():
    with pytest.raises(ValidationError):
        Project(owner_id="dev-user", name="nowhere")


def test_work_item_defaults_to_draft():
    w = WorkItem(project_id="p1", kind=WorkItemKind.EPIC, title="Auth")
    assert w.status == WorkItemStatus.DRAFT
    assert w.acceptance_criteria == []


def test_epic_cannot_have_parent():
    with pytest.raises(ValidationError):
        WorkItem(project_id="p1", kind=WorkItemKind.EPIC, title="x", parent_id="other")


def test_task_requires_parent():
    with pytest.raises(ValidationError):
        WorkItem(project_id="p1", kind=WorkItemKind.TASK, title="x")


def test_roles_enum_has_core_roles():
    assert {"lead", "architect", "backend", "frontend", "qa", "devops"} <= {
        r.value for r in AgentRole
    }
