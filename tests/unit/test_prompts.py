from domain.agent import prompts
from domain.agent.prompts import for_stage
from domain.runs import RunStage


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


# Task 1: Memory pointer tests
def test_plan_prompt_points_to_project_memory():
    prompt, tools = for_stage(RunStage.PLAN, "Add login", ["works"])
    assert "CLAUDE.md" in prompt
    assert "AGENTS.md" in prompt
    assert "docs/adr" in prompt
    assert "Read" in tools


def test_implement_prompt_points_to_project_memory():
    prompt, _ = for_stage(RunStage.IMPLEMENT, "Add login", ["works"])
    assert "CLAUDE.md" in prompt
    assert "docs/adr" in prompt


def test_verify_prompt_has_no_memory_pointer():
    prompt, _ = for_stage(RunStage.VERIFY, "Add login", ["works"])
    assert "CLAUDE.md" not in prompt


# Task 2: LEARN prompt tests
def test_learn_prompt_requests_additions_and_deletions():
    prompt, tools = for_stage(RunStage.LEARN, "Add login", ["works"])
    lowered = prompt.lower()
    assert "additions" in lowered or "add" in lowered
    assert "deletion" in lowered or "remove" in lowered
    assert "CLAUDE.md" in prompt
    assert "docs/adr" in prompt
    assert "Edit" in tools  # editing existing memory files


def test_for_stage_learn_includes_task_context():
    from domain.agent.prompts import for_stage
    from domain.runs import RunStage
    prompt, tools = for_stage(RunStage.LEARN, "Add OAuth login",
                              ["users can log in with Google"], body="see ticket")
    assert "project memory" in prompt.lower()
    assert tools == ["Read", "Edit", "Write"]
    assert "Add OAuth login" in prompt
    assert "users can log in with Google" in prompt


def test_memory_pointer_with_and_without_role():
    from domain.agent.models import AgentRole
    from domain.agent.prompts import memory_pointer
    p = memory_pointer(AgentRole.BACKEND, role_digest="- prefer small PRs")
    assert "CLAUDE.md" in p and "docs/adr" in p
    assert "backend" in p and "prefer small PRs" in p
    assert ".orchestration/role-memory.md" in p
    none = memory_pointer(None, role_digest="")
    assert "CLAUDE.md" in none and "role-memory.md" not in none
