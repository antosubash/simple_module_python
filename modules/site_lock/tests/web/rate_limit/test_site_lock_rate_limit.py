"""In-memory per-IP attempt limiter."""

from __future__ import annotations

import pytest
from site_lock.web.rate_limit import AttemptLimiter


def _limiter() -> AttemptLimiter:
    return AttemptLimiter(max_failures=3, window_seconds=100, cooldown_seconds=500)


def test_fresh_key_is_not_blocked() -> None:
    assert _limiter().is_blocked("1.2.3.4", now=0.0) is False


def test_blocks_after_max_failures() -> None:
    lim = _limiter()
    for i in range(3):
        lim.record_failure("1.2.3.4", now=float(i))
    assert lim.is_blocked("1.2.3.4", now=3.0) is True


def test_under_the_limit_is_not_blocked() -> None:
    lim = _limiter()
    for i in range(2):
        lim.record_failure("1.2.3.4", now=float(i))
    assert lim.is_blocked("1.2.3.4", now=3.0) is False


def test_failures_outside_the_window_do_not_accumulate() -> None:
    lim = _limiter()
    lim.record_failure("1.2.3.4", now=0.0)
    lim.record_failure("1.2.3.4", now=1.0)
    # 500s later the first two have aged out of the 100s window.
    lim.record_failure("1.2.3.4", now=500.0)
    assert lim.is_blocked("1.2.3.4", now=500.0) is False


def test_cooldown_expires() -> None:
    lim = _limiter()
    for i in range(3):
        lim.record_failure("1.2.3.4", now=float(i))
    assert lim.is_blocked("1.2.3.4", now=3.0) is True
    assert lim.is_blocked("1.2.3.4", now=600.0) is False


def test_keys_are_independent() -> None:
    lim = _limiter()
    for i in range(3):
        lim.record_failure("1.1.1.1", now=float(i))
    assert lim.is_blocked("1.1.1.1", now=3.0) is True
    assert lim.is_blocked("2.2.2.2", now=3.0) is False


def test_reset_clears_a_block() -> None:
    lim = _limiter()
    for i in range(3):
        lim.record_failure("1.2.3.4", now=float(i))
    lim.reset("1.2.3.4")
    assert lim.is_blocked("1.2.3.4", now=3.0) is False


def test_expired_keys_are_collected_without_dropping_live_cooldowns():
    lim = _limiter()
    lim.record_failure("stale", now=0)
    for i in range(3):
        lim.record_failure("blocked", now=90 + i)
    lim.record_failure("fresh", now=101)
    assert "stale" not in lim._buckets
    assert lim.is_blocked("blocked", now=101)
    lim.is_blocked("visitor", now=700)
    assert not lim._buckets


def test_capacity_evicts_oldest_and_remains_bounded():
    lim = AttemptLimiter(max_failures=1, window_seconds=100, cooldown_seconds=500, max_buckets=2)
    for i in range(10):
        lim.record_failure(str(i), now=i)
        assert len(lim._buckets) <= 2
    assert list(lim._buckets) == ["8", "9"]


def test_capacity_sweeps_expired_before_oldest_live_bucket():
    lim = AttemptLimiter(max_failures=2, window_seconds=100, cooldown_seconds=500, max_buckets=2)
    lim.record_failure("live", now=0)
    lim.record_failure("live", now=0)
    lim.record_failure("expired", now=1)
    lim.is_blocked("live", now=100)  # Next periodic sweep is at 200.
    lim.record_failure("new", now=102)
    assert set(lim._buckets) == {"live", "new"}


@pytest.mark.parametrize("bad_max", [0, -1])
def test_non_positive_max_buckets_rejected(bad_max: int):
    with pytest.raises(ValueError, match="max_buckets"):
        AttemptLimiter(
            max_failures=1, window_seconds=100, cooldown_seconds=500, max_buckets=bad_max
        )


def test_capacity_one_and_existing_key_update_preserve_bucket():
    lim = AttemptLimiter(max_failures=2, window_seconds=100, cooldown_seconds=500, max_buckets=1)
    lim.record_failure("k1", now=1)
    lim.record_failure("k1", now=2)
    assert lim.is_blocked("k1", now=3) is True

    lim2 = AttemptLimiter(max_failures=2, window_seconds=100, cooldown_seconds=500, max_buckets=2)
    lim2.record_failure("a", now=1)
    lim2.record_failure("b", now=2)
    lim2.record_failure("a", now=3)
    assert lim2.is_blocked("a", now=4) is True
    assert set(lim2._buckets) == {"a", "b"}
