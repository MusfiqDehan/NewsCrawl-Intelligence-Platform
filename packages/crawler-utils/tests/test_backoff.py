from newscrawl_crawler_utils.backoff import compute_backoff_seconds


def test_backoff_grows_exponentially() -> None:
    d1 = compute_backoff_seconds(1, jitter_ratio=0)
    d2 = compute_backoff_seconds(2, jitter_ratio=0)
    d3 = compute_backoff_seconds(3, jitter_ratio=0)
    assert d2 == d1 * 2
    assert d3 == d1 * 4


def test_backoff_capped() -> None:
    assert compute_backoff_seconds(50, jitter_ratio=0) == 6 * 3600.0


def test_jitter_within_bounds() -> None:
    for _ in range(100):
        delay = compute_backoff_seconds(2, base_seconds=60, jitter_ratio=0.2)
        assert 96.0 <= delay <= 144.0


def test_zero_retry_treated_as_first() -> None:
    assert compute_backoff_seconds(0, jitter_ratio=0) == compute_backoff_seconds(1, jitter_ratio=0)
