"""In-memory per-IP attempt limiter."""

from __future__ import annotations

from site_lock.rate_limit import AttemptLimiter


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
