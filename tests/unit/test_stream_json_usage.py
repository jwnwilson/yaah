import json

from adapters.agent.runtime import stream_json
from domain.runs import RunStage


def _result_line(**result_obj):
    return json.dumps({"type": "result", **result_obj})


def test_parse_captures_top_level_usage():
    line = _result_line(
        is_error=False,
        result="done",
        total_cost_usd=0.42,
        usage={
            "input_tokens": 100,
            "output_tokens": 30,
            "cache_read_input_tokens": 5,
            "cache_creation_input_tokens": 7,
        },
    )
    _events, result = stream_json.parse([line], RunStage.IMPLEMENT)
    assert result.usage.input_tokens == 100
    assert result.usage.output_tokens == 30
    assert result.usage.cache_read_tokens == 5
    assert result.usage.cache_creation_tokens == 7
    assert round(result.usage.cost_usd, 2) == 0.42


def test_parse_splits_model_usage_per_model():
    line = _result_line(
        is_error=False,
        result="done",
        total_cost_usd=0.9,
        usage={"input_tokens": 150, "output_tokens": 50},
        modelUsage={
            "claude-opus-4-8": {"inputTokens": 100, "outputTokens": 30,
                                "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0,
                                "costUSD": 0.6},
            "claude-haiku-4-5": {"inputTokens": 50, "outputTokens": 20,
                                 "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0,
                                 "costUSD": 0.3},
        },
    )
    _events, result = stream_json.parse([line], RunStage.IMPLEMENT)
    assert set(result.model_usage) == {"claude-opus-4-8", "claude-haiku-4-5"}
    assert result.model_usage["claude-opus-4-8"].input_tokens == 100
    assert round(result.model_usage["claude-haiku-4-5"].cost_usd, 2) == 0.3


def test_parse_tolerates_missing_usage():
    line = _result_line(is_error=False, result="done", total_cost_usd=0.1)
    _events, result = stream_json.parse([line], RunStage.IMPLEMENT)
    assert result.usage.total_tokens == 0
    assert result.model_usage == {}
