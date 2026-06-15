"""Unit tests for epic-focused refinement contract additions."""
from domain.models import WorkItem, WorkItemKind
from domain.refinement import (
    EpicSpecEdit,
    RefinementContext,
    RefinementOutput,
    epic_focus_prompt,
)


def test_epic_focus_prompt_names_epic_and_instructs_breakdown():
    epic = WorkItem(owner_id="u", project_id="p", kind=WorkItemKind.EPIC, title="Checkout")
    prompt = epic_focus_prompt(epic)
    assert "Checkout" in prompt
    assert epic.id in prompt
    assert "feature" in prompt.lower()


def test_refinement_output_parses_epic_update():
    out = RefinementOutput(**{"reply": "ok", "epic_update": {"body": "new", "acceptance_criteria": ["a"]}})
    assert isinstance(out.epic_update, EpicSpecEdit)
    assert out.epic_update.body == "new"
    assert out.epic_update.acceptance_criteria == ["a"]


def test_refinement_output_epic_update_defaults_none():
    assert RefinementOutput(reply="hi").epic_update is None


def test_refinement_context_carries_epic_id():
    ctx = RefinementContext(project_name="p", epic_id="e1")
    assert ctx.epic_id == "e1"
    assert RefinementContext(project_name="p").epic_id is None
