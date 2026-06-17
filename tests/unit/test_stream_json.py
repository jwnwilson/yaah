import json

from adapters.agent.runtime.stream_json import parse
from domain.runs import RunStage


def _lines(*objs):
    return [json.dumps(o) for o in objs]


def test_parses_progress_and_result_with_cost():
    lines = _lines(
        {"type": "system", "subtype": "init"},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "working on it"}]}},
        {"type": "result", "subtype": "success", "is_error": False,
         "total_cost_usd": 0.42, "result": "done"},
    )
    events, result = parse(lines, RunStage.IMPLEMENT)
    assert any(e.type == "progress" and "working" in e.message for e in events)
    assert events[-1].type == "result"
    assert result.outcome == "ok" and result.cost_usd == 0.42


def test_is_error_maps_to_fail():
    lines = _lines({"type": "result", "is_error": True, "total_cost_usd": 0.1})
    _events, result = parse(lines, RunStage.VERIFY)
    assert result.outcome == "fail"


def test_ignores_blank_and_unknown_lines():
    events, result = parse(["", "not json", json.dumps({"type": "whatever"})], RunStage.PLAN)
    assert result.outcome == "ok"  # default; no result line
    assert events == [] or all(e.type != "result" for e in events)
