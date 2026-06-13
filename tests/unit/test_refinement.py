import pytest

from domain.models import WorkItemKind
from domain.refinement import (
    RefinementOutput,
    WorkItemProposal,
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
