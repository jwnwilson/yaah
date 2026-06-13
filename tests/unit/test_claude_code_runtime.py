import json

from adapters.model.fake import FakeModelProvider
from adapters.runtime.claude_code import ClaudeCodeRuntime
from domain.models import RunStage
from domain.runtime import RunContext


class _FakeProc:
    def __init__(self, lines):
        self.stdout = iter(lines)
        self.stderr = iter([])
        self.pid = 4321
        self.returncode = 0

    def wait(self):
        return 0


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
    from adapters.runtime.fake import result_of
    assert result_of(events).cost_usd == 0.5


def test_run_stage_fail_when_no_result_event():
    def spawn(argv, **kw):
        return _FakeProc([])  # claude died with no output

    rt = ClaudeCodeRuntime(FakeModelProvider(), spawn=spawn)
    events = list(rt.run_stage(_ctx()))
    from adapters.runtime.fake import result_of
    assert result_of(events).outcome == "fail"
