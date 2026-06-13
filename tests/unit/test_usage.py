from domain.usage import ZERO_USAGE, TokenUsage, group_by, rollup


def test_total_tokens_sums_all_four_buckets():
    u = TokenUsage(input_tokens=10, output_tokens=20, cache_read_tokens=3, cache_creation_tokens=4)
    assert u.total_tokens == 37


def test_combine_returns_new_object_and_does_not_mutate():
    a = TokenUsage(input_tokens=10, cost_usd=0.10)
    b = TokenUsage(input_tokens=5, output_tokens=2, cost_usd=0.05)
    c = a.combine(b)
    assert c.input_tokens == 15
    assert c.output_tokens == 2
    assert round(c.cost_usd, 2) == 0.15
    assert a.input_tokens == 10  # unchanged (immutability)


def test_rollup_sums_an_iterable():
    items = [TokenUsage(input_tokens=1, cost_usd=0.01), TokenUsage(input_tokens=2, cost_usd=0.02)]
    total = rollup(items)
    assert total.input_tokens == 3
    assert round(total.cost_usd, 2) == 0.03


def test_rollup_of_empty_is_zero():
    assert rollup([]) == ZERO_USAGE


def test_group_by_buckets_by_key():
    rows = [
        ("plan", TokenUsage(input_tokens=1)),
        ("plan", TokenUsage(input_tokens=2)),
        ("verify", TokenUsage(input_tokens=4)),
    ]
    grouped = group_by(rows)
    assert grouped["plan"].input_tokens == 3
    assert grouped["verify"].input_tokens == 4
