from adapters.agent.runtime.fake import _default_events
from domain.agent import result_of
from domain.runs import RunStage


def test_default_result_event_carries_model_usage():
    events = _default_events(RunStage.IMPLEMENT)
    result = result_of(events)
    assert result.cost_usd > 0
    assert result.model_usage, "fake stage should report at least one model's usage"
    only = next(iter(result.model_usage.values()))
    assert only.total_tokens > 0
