from interactors.temporal.worker import build_activities


def test_build_activities_returns_four_callables():
    acts = build_activities("sqlite:///:memory:")
    assert len(acts) == 4
    assert all(callable(a) for a in acts)
