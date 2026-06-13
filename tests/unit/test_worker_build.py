from interactors.temporal.worker import build_activities


def test_build_activities_returns_six():
    acts = build_activities("sqlite:///:memory:", profile="local")
    assert len(acts) == 6
    assert all(callable(a) for a in acts)
