from adapters.temporal.worker import build_activities


def test_build_activities_returns_three_callables():
    acts = build_activities("sqlite:///:memory:")
    assert len(acts) == 3
    assert all(callable(a) for a in acts)
