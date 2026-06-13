from domain import prompts
from domain.models import RunStage


def test_implement_prompt_has_edit_tools_and_criteria():
    text, tools = prompts.for_stage(RunStage.IMPLEMENT, "Add login", ["works", "tested"], "do it")
    assert "Add login" in text and "- works" in text
    assert "Edit" in tools and "Bash" in tools


def test_verify_is_read_only():
    _text, tools = prompts.for_stage(RunStage.VERIFY, "X", [], "")
    assert "Edit" not in tools and "Write" not in tools
    assert "Bash" in tools


def test_max_turns_implement_highest():
    assert prompts.max_turns(RunStage.IMPLEMENT) >= prompts.max_turns(RunStage.VERIFY)
