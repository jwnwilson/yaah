import json

from domain.agent import (
    AgentInvocation,
    AgentManifest,
    McpRef,
    RunContext,
    SkillRef,
    build_invocation,
)
from domain.models import RunStage


def _ctx(stage=RunStage.IMPLEMENT, **kw):
    base = dict(run_id="r1", stage=stage, task_title="Add login",
                acceptance_criteria=["works"], workspace_path="/ws")
    base.update(kw)
    return RunContext(**base)


def test_no_agent_argv_has_core_flags_and_no_extras():
    inv = build_invocation(_ctx(), model_id="sonnet")

    assert isinstance(inv, AgentInvocation)
    assert inv.argv[0] == "claude"
    assert "-p" in inv.argv
    assert "--output-format" in inv.argv and "stream-json" in inv.argv
    assert "--verbose" in inv.argv
    assert inv.argv.count("--allowedTools") == 1
    assert inv.argv.count("--max-turns") == 1
    i = inv.argv.index("--model")
    assert inv.argv[i + 1] == "sonnet"
    # no agent -> no settings/mcp files, no extra env, no skills, no mcp flag
    assert inv.files == {}
    assert inv.env_extra == {}
    assert inv.skills == []
    assert inv.mcp_config_path is None
    assert "--append-system-prompt" not in inv.argv
    assert "--mcp-config" not in inv.argv


def test_agent_tools_override_stage_defaults():
    man = AgentManifest(allowed_tools=["MyTool"])
    inv = build_invocation(_ctx(agent=man), model_id="sonnet")

    i = inv.argv.index("--allowedTools")
    rest = inv.argv[i + 1:]
    end = next((j for j, a in enumerate(rest) if a.startswith("--")), len(rest))
    assert rest[:end] == ["MyTool"]


def test_agent_empty_tools_fall_back_to_stage_defaults():
    from domain.agent import prompts
    man = AgentManifest(allowed_tools=[])
    inv = build_invocation(_ctx(agent=man), model_id="sonnet")

    _, defaults = prompts.for_stage(RunStage.IMPLEMENT, "T", [], "")
    for t in defaults:
        assert t in inv.argv


def test_system_prompt_skills_and_mcp_compose():
    man = AgentManifest(
        system_prompt="you are eng",
        allowed_tools=["Read", "Edit"],
        skills=[SkillRef(name="pytest", source="git@x/s.git")],
        mcp_servers=[McpRef(name="fs", transport="stdio",
                            command_or_url="npx mcp-fs",
                            tool_allowlist=["mcp__fs__read"])],
    )
    inv = build_invocation(_ctx(agent=man, workspace_path="/ws"), model_id="sonnet")

    assert "--append-system-prompt" in inv.argv and "you are eng" in inv.argv
    assert "mcp__fs__read" in inv.argv          # mcp allowlist merged into tools
    assert "--mcp-config" in inv.argv
    assert inv.mcp_config_path == "/ws/.mcp.json"
    assert inv.skills == [("pytest", "git@x/s.git", "/ws/.claude/skills/pytest")]
    cfg = json.loads(inv.files[".mcp.json"])
    assert cfg["mcpServers"]["fs"]["command"] == "npx mcp-fs"


def test_no_mcp_means_no_mcp_file_or_flag():
    man = AgentManifest(system_prompt="sp")
    inv = build_invocation(_ctx(agent=man), model_id="sonnet")

    assert "--mcp-config" not in inv.argv
    assert ".mcp.json" not in inv.files
    assert inv.mcp_config_path is None


def test_secret_env_in_env_extra_and_mcp_file():
    man = AgentManifest(
        allowed_tools=["Read"],
        secret_env={"GH_TOKEN": "ghp_x"},
        mcp_servers=[McpRef(name="fs", transport="stdio", command_or_url="npx mcp-fs")],
    )
    inv = build_invocation(_ctx(agent=man, workspace_path="/ws"), model_id="sonnet")

    assert inv.env_extra["GH_TOKEN"] == "ghp_x"
    cfg = json.loads(inv.files[".mcp.json"])
    assert cfg["mcpServers"]["fs"]["env"]["GH_TOKEN"] == "ghp_x"


def test_yaah_env_block_set_when_agent_present():
    man = AgentManifest(allowed_tools=["Read", "Edit"])
    inv = build_invocation(_ctx(agent=man, run_id="r1", workspace_path="/ws"), model_id="sonnet")

    assert json.loads(inv.env_extra["YAAH_ALLOWED_TOOLS"]) == ["Read", "Edit"]
    assert inv.env_extra["YAAH_AUDIT_PATH"] == "/ws/audit.jsonl"
    assert inv.env_extra["YAAH_RUN_ID"] == "r1"
    assert inv.env_extra["YAAH_STAGE"] == "implement"
    assert "PreToolUse" in inv.files[".claude/settings.json"]
    assert "pretooluse_hook" in inv.files[".claude/settings.json"]


def test_model_id_is_used_verbatim():
    man = AgentManifest(allowed_tools=["Read"])
    inv = build_invocation(_ctx(agent=man), model_id="mid")
    i = inv.argv.index("--model")
    assert inv.argv[i + 1] == "mid"


def test_run_context_accepts_instructions():
    from domain.agent import RunContext
    from domain.models import RunStage

    ctx = RunContext(run_id="r1", stage=RunStage.IMPLEMENT, task_title="t",
                     workspace_path="/tmp/x", instructions="do exactly this")
    assert ctx.instructions == "do exactly this"


def test_build_invocation_uses_instructions_when_present():
    from domain.agent import RunContext, build_invocation
    from domain.models import RunStage

    ctx = RunContext(run_id="r1", stage=RunStage.IMPLEMENT, task_title="t",
                     acceptance_criteria=["c"], workspace_path="/tmp/x",
                     instructions="ORCHESTRATED BRIEF: build the widget")
    inv = build_invocation(ctx, model_id="m")
    p = inv.argv.index("-p")
    assert inv.argv[p + 1] == "ORCHESTRATED BRIEF: build the widget"


def test_build_invocation_falls_back_to_stage_prompt():
    from domain.agent import RunContext, build_invocation
    from domain.models import RunStage

    ctx = RunContext(run_id="r1", stage=RunStage.IMPLEMENT, task_title="Add login",
                     acceptance_criteria=["works"], workspace_path="/tmp/x")
    inv = build_invocation(ctx, model_id="m")
    p = inv.argv.index("-p")
    assert "Add login" in inv.argv[p + 1]
