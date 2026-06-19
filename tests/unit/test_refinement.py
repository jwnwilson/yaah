import pytest

from domain.projects import WorkItem, WorkItemKind, WorkItemStatus
from domain.refinement import (
    CommitPlan,
    RefinementAction,
    RefinementOutput,
    WorkItemProposal,
    select_committable,
    system_prompt,
    validate_proposal,
)


def test_output_and_proposal_shapes():
    out = RefinementOutput(reply="ok", proposals=[
        WorkItemProposal(kind=WorkItemKind.EPIC, title="Auth")])
    assert out.reply == "ok" and out.proposals[0].title == "Auth"


def test_validate_epic_rejects_parent():
    with pytest.raises(ValueError):
        validate_proposal(WorkItemProposal(kind=WorkItemKind.EPIC, parent_id="x", title="E"),
                          parent_exists=lambda pid: True)


def test_validate_feature_requires_existing_parent():
    with pytest.raises(ValueError):
        validate_proposal(WorkItemProposal(kind=WorkItemKind.FEATURE, title="F"),
                          parent_exists=lambda pid: True)            # no parent_id
    with pytest.raises(ValueError):
        validate_proposal(
            WorkItemProposal(kind=WorkItemKind.FEATURE, parent_id="missing", title="F"),
            parent_exists=lambda pid: False,  # parent not found
        )
    validate_proposal(WorkItemProposal(kind=WorkItemKind.FEATURE, parent_id="e1", title="F"),
                      parent_exists=lambda pid: True)                # ok


def test_system_prompt_mentions_project_and_drafts():
    p = system_prompt("Alpha", "You are the lead.")
    assert "Alpha" in p and "draft" in p.lower()


def test_system_prompt_explains_confirm_then_commit():
    p = system_prompt("Alpha").lower()
    assert "confirm" in p and "commit" in p


def test_output_action_defaults_to_discuss():
    out = RefinementOutput(reply="hi")
    assert out.action == RefinementAction.DISCUSS


def test_output_parses_commit_action():
    out = RefinementOutput(**{"reply": "starting", "action": "commit"})
    assert out.action == RefinementAction.COMMIT


def test_select_committable_picks_draft_tasks_and_their_parents():
    epic = WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.EPIC, title="E")
    feat = WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.FEATURE,
                    parent_id=epic.id, title="F")
    ready_task = WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.TASK,
                          parent_id=feat.id, title="done", status=WorkItemStatus.READY)
    draft_task = WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.TASK,
                          parent_id=feat.id, title="todo", status=WorkItemStatus.DRAFT)

    plan = select_committable([epic, feat, ready_task, draft_task])

    assert plan.task_ids == [draft_task.id]          # only the DRAFT task
    assert plan.parent_ids == [feat.id]              # its direct parent, deduped


def test_select_committable_dedups_shared_parent_and_handles_empty():
    assert select_committable([]) == CommitPlan(task_ids=[], parent_ids=[])

    feat = WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.FEATURE,
                    parent_id="e1", title="F")
    t1 = WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.TASK,
                  parent_id=feat.id, title="a", status=WorkItemStatus.DRAFT)
    t2 = WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.TASK,
                  parent_id=feat.id, title="b", status=WorkItemStatus.DRAFT)

    plan = select_committable([feat, t1, t2])

    assert plan.task_ids == [t1.id, t2.id]
    assert plan.parent_ids == [feat.id]   # shared parent deduped to one
