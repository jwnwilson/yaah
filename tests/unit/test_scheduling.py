from domain.projects.scheduling import plan_starts


def test_plan_starts_fills_free_slots_in_order():
    assert plan_starts(["a", "b", "c"], in_flight=1, limit=2) == ["a"]


def test_plan_starts_returns_all_when_room():
    assert plan_starts(["a", "b"], in_flight=0, limit=5) == ["a", "b"]


def test_plan_starts_empty_when_full():
    assert plan_starts(["a", "b"], in_flight=2, limit=2) == []


def test_plan_starts_empty_when_over_capacity():
    assert plan_starts(["a"], in_flight=3, limit=2) == []


def test_plan_starts_empty_queue():
    assert plan_starts([], in_flight=0, limit=2) == []
