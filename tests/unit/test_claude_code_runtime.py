import json
import os
import tempfile

from adapters.agent.model.fake import FakeModelProvider
from adapters.agent.runtime.claude_code import ClaudeCodeRuntime
from domain.agent import RunContext
from domain.models import RunStage


class _FakeProc:
    def __init__(self, lines):
        self.stdout = iter(lines)
        self.stderr = iter([])
        self.pid = 4321
        self.returncode = 0

    def wait(self):
        return 0


def _result_line():
    return json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0.1})


def _ctx(stage=RunStage.IMPLEMENT):
    return RunContext(run_id="r1", stage=stage, task_title="Add login",
                     acceptance_criteria=["works"], workspace_path="/ws")


def test_run_stage_streams_events_and_result():
    lines = [
        json.dumps({"type": "assistant",
                    "message": {"content": [{"type": "text", "text": "editing"}]}}),
        json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0.5, "result": "ok"}),
    ]
    captured = {}

    def spawn(argv, **kw):
        captured["argv"] = argv
        captured["cwd"] = kw.get("cwd")
        return _FakeProc(lines)

    rt = ClaudeCodeRuntime(FakeModelProvider(), spawn=spawn)
    events = list(rt.run_stage(_ctx()))
    assert captured["cwd"] == "/ws"
    assert "claude" in captured["argv"][0]
    assert "--output-format" in captured["argv"] and "stream-json" in captured["argv"]
    assert events[-1].type == "result"
    from adapters.agent.runtime.fake import result_of
    assert result_of(events).cost_usd == 0.5


def test_run_stage_fail_when_no_result_event():
    def spawn(argv, **kw):
        return _FakeProc([])  # claude died with no output

    rt = ClaudeCodeRuntime(FakeModelProvider(), spawn=spawn)
    events = list(rt.run_stage(_ctx()))
    from adapters.agent.runtime.fake import result_of
    assert result_of(events).outcome == "fail"


# --- T4 tests: composition from AgentManifest ---

def test_composes_system_prompt_tools_skills_and_mcp():
    from adapters.skills.fake import FakeSkillFetcher
    from domain.agent import AgentManifest, McpRef, SkillRef

    ws = tempfile.mkdtemp()
    man = AgentManifest(
        system_prompt="you are eng",
        allowed_tools=["Read", "Edit"],
        skills=[SkillRef(name="pytest", source="git@x/s.git")],
        mcp_servers=[McpRef(name="fs", transport="stdio",
                            command_or_url="npx mcp-fs",
                            tool_allowlist=["mcp__fs__read"])],
    )
    ctx = RunContext(run_id="r1", stage=RunStage.IMPLEMENT, task_title="T",
                     acceptance_criteria=[], workspace_path=ws, agent=man)
    captured = {}

    def spawn(argv, **kw):
        captured["argv"] = argv
        return _FakeProc([_result_line()])

    fetcher = FakeSkillFetcher()
    rt = ClaudeCodeRuntime(FakeModelProvider(), spawn=spawn, skills=fetcher)
    list(rt.run_stage(ctx))

    argv = captured["argv"]
    assert "--append-system-prompt" in argv and "you are eng" in argv
    assert "Read" in argv and "Edit" in argv and "mcp__fs__read" in argv
    assert "--mcp-config" in argv
    assert fetcher.fetched and fetcher.fetched[0][0] == "git@x/s.git"
    assert os.path.exists(os.path.join(ws, ".mcp.json"))


def test_agent_tools_override_stage_defaults():
    from adapters.skills.fake import FakeSkillFetcher
    from domain.agent import AgentManifest

    ws = tempfile.mkdtemp()
    man = AgentManifest(allowed_tools=["MyTool"])
    ctx = RunContext(run_id="r1", stage=RunStage.IMPLEMENT, task_title="T",
                     workspace_path=ws, agent=man)
    captured = {}

    def spawn(argv, **kw):
        captured["argv"] = argv
        return _FakeProc([_result_line()])

    rt = ClaudeCodeRuntime(FakeModelProvider(), spawn=spawn, skills=FakeSkillFetcher())
    list(rt.run_stage(ctx))

    argv = captured["argv"]
    idx = argv.index("--allowedTools")
    tools_in_argv = argv[idx + 1:]
    # next flag marks end of tools list
    end = next((i for i, a in enumerate(tools_in_argv) if a.startswith("--")), len(tools_in_argv))
    tools = tools_in_argv[:end]
    assert "MyTool" in tools
    # stage defaults should NOT be duplicated alongside agent tools
    assert argv.count("--allowedTools") == 1


def test_agent_empty_tools_fallback_to_stage_defaults():
    from adapters.skills.fake import FakeSkillFetcher
    from domain.agent import AgentManifest, prompts

    ws = tempfile.mkdtemp()
    man = AgentManifest(allowed_tools=[])  # empty -> fallback
    ctx = RunContext(run_id="r1", stage=RunStage.IMPLEMENT, task_title="T",
                     workspace_path=ws, agent=man)
    captured = {}

    def spawn(argv, **kw):
        captured["argv"] = argv
        return _FakeProc([_result_line()])

    rt = ClaudeCodeRuntime(FakeModelProvider(), spawn=spawn, skills=FakeSkillFetcher())
    list(rt.run_stage(ctx))

    _, stage_defaults = prompts.for_stage(RunStage.IMPLEMENT, "T", [], "")
    argv = captured["argv"]
    for t in stage_defaults:
        assert t in argv


def test_no_mcp_config_when_no_mcp_servers():
    from adapters.skills.fake import FakeSkillFetcher
    from domain.agent import AgentManifest

    ws = tempfile.mkdtemp()
    man = AgentManifest(system_prompt="sp")  # no mcp_servers
    ctx = RunContext(run_id="r1", stage=RunStage.IMPLEMENT, task_title="T",
                     workspace_path=ws, agent=man)
    captured = {}

    def spawn(argv, **kw):
        captured["argv"] = argv
        return _FakeProc([_result_line()])

    rt = ClaudeCodeRuntime(FakeModelProvider(), spawn=spawn, skills=FakeSkillFetcher())
    list(rt.run_stage(ctx))

    assert "--mcp-config" not in captured["argv"]
    assert not os.path.exists(os.path.join(ws, ".mcp.json"))


def test_skill_fetch_failure_is_skipped_not_fatal():
    from adapters.agent.runtime.fake import result_of
    from adapters.skills.fake import FakeSkillFetcher
    from domain.agent import AgentManifest, SkillRef

    ws = tempfile.mkdtemp()
    man = AgentManifest(skills=[SkillRef(name="bad", source="git@x/bad.git")])
    ctx = RunContext(run_id="r1", stage=RunStage.IMPLEMENT, task_title="T",
                     workspace_path=ws, agent=man)

    rt = ClaudeCodeRuntime(
        FakeModelProvider(),
        spawn=lambda a, **k: _FakeProc([_result_line()]),
        skills=FakeSkillFetcher(fail_on="git@x/bad.git"),
    )
    events = list(rt.run_stage(ctx))
    assert result_of(events).outcome == "ok"  # run continued despite the bad skill
    # a warning event is emitted for the skipped skill
    skip_events = [e for e in events if "skipped" in e.message]
    assert skip_events


def test_secret_env_injected_into_subprocess_and_mcp():
    import json
    import os
    import tempfile

    from adapters.skills.fake import FakeSkillFetcher
    from domain.agent import AgentManifest, McpRef

    ws = tempfile.mkdtemp()
    man = AgentManifest(
        allowed_tools=["Read"],
        secret_env={"GH_TOKEN": "ghp_x"},
        mcp_servers=[McpRef(name="fs", transport="stdio", command_or_url="npx mcp-fs")],
    )
    ctx = RunContext(run_id="r1", stage=RunStage.IMPLEMENT, task_title="T",
                     workspace_path=ws, agent=man)
    captured = {}

    class _P:
        def __init__(self):
            result = json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0})
            self.stdout = iter([result])
            self.stderr = iter([])
            self.pid = 1

        def wait(self):
            return 0

    def spawn(argv, **kw):
        captured["env"] = kw.get("env", {})
        return _P()

    rt = ClaudeCodeRuntime(FakeModelProvider(), spawn=spawn, skills=FakeSkillFetcher())
    list(rt.run_stage(ctx))
    assert captured["env"].get("GH_TOKEN") == "ghp_x"
    cfg = json.load(open(os.path.join(ws, ".mcp.json")))
    assert cfg["mcpServers"]["fs"]["env"]["GH_TOKEN"] == "ghp_x"


def test_model_alias_overrides_model_flag():
    import json
    import tempfile

    from adapters.skills.fake import FakeSkillFetcher
    from domain.agent import AgentManifest, RunContext

    man = AgentManifest(allowed_tools=["Read"], model_alias="engineer-model")
    ctx = RunContext(run_id="r1", stage=RunStage.IMPLEMENT, task_title="T",
                     workspace_path=tempfile.mkdtemp(), agent=man)
    captured = {}

    result_json = json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0})

    class _P:
        def __init__(s):
            s.stdout = iter([result_json])
            s.stderr = iter([])
            s.pid = 1

        def wait(s):
            return 0

    def spawn(argv, **kw):
        captured["argv"] = argv
        return _P()

    rt = ClaudeCodeRuntime(FakeModelProvider(), spawn=spawn, skills=FakeSkillFetcher())
    list(rt.run_stage(ctx))
    i = captured["argv"].index("--model")
    assert captured["argv"][i + 1] == "engineer-model"  # alias, not provider default


def test_no_agent_path_unchanged():
    """ctx.agent=None must produce the same argv as before T4 (no double flags)."""
    lines = [json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0.0})]
    captured = {}

    def spawn(argv, **kw):
        captured["argv"] = argv
        return _FakeProc(lines)

    rt = ClaudeCodeRuntime(FakeModelProvider(), spawn=spawn)
    list(rt.run_stage(_ctx()))

    argv = captured["argv"]
    assert argv.count("--allowedTools") == 1
    assert argv.count("--max-turns") == 1
    assert argv.count("--model") == 1
    assert "--append-system-prompt" not in argv
    assert "--mcp-config" not in argv


def test_runtime_writes_pretooluse_hook_and_env():
    from adapters.skills.fake import FakeSkillFetcher
    from domain.agent import AgentManifest

    ws = tempfile.mkdtemp()
    man = AgentManifest(allowed_tools=["Read", "Edit"])
    ctx = RunContext(run_id="r1", stage=RunStage.IMPLEMENT, task_title="T",
                     acceptance_criteria=[], workspace_path=ws, agent=man)
    captured = {}

    class _P:
        def __init__(s):
            result = json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0})
            s.stdout = iter([result])
            s.stderr = iter([])
            s.pid = 1

        def wait(s):
            return 0

    def spawn(argv, **kw):
        captured["env"] = kw.get("env", {})
        return _P()

    rt = ClaudeCodeRuntime(FakeModelProvider(), spawn=spawn, skills=FakeSkillFetcher())
    list(rt.run_stage(ctx))

    settings = json.load(open(os.path.join(ws, ".claude", "settings.json")))
    assert "PreToolUse" in settings["hooks"]
    assert "pretooluse_hook" in json.dumps(settings["hooks"])
    assert json.loads(captured["env"]["YAAH_ALLOWED_TOOLS"]) == ["Read", "Edit"]
    assert captured["env"]["YAAH_AUDIT_PATH"].endswith("audit.jsonl")
    assert captured["env"]["YAAH_RUN_ID"] == "r1"
    assert captured["env"]["YAAH_STAGE"] == "implement"


def test_no_agent_no_settings_no_yaah_env():
    """ctx.agent=None: no settings.json written, no YAAH_* env vars injected."""
    captured = {}

    def spawn(argv, **kw):
        captured["env"] = kw.get("env", {})
        return _FakeProc([json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0.0})])

    ws = tempfile.mkdtemp()
    ctx = RunContext(run_id="r2", stage=RunStage.IMPLEMENT, task_title="T",
                     acceptance_criteria=[], workspace_path=ws)
    rt = ClaudeCodeRuntime(FakeModelProvider(), spawn=spawn)
    list(rt.run_stage(ctx))

    assert not os.path.exists(os.path.join(ws, ".claude", "settings.json"))
    assert "YAAH_ALLOWED_TOOLS" not in captured["env"]
    assert "YAAH_AUDIT_PATH" not in captured["env"]
    assert "YAAH_RUN_ID" not in captured["env"]
    assert "YAAH_STAGE" not in captured["env"]
