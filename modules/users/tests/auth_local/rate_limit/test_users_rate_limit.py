"""Tests for ThroughputLimiter."""

from __future__ import annotations

from users.auth_local.rate_limit import ThroughputLimiter


class TestThroughputLimiter:
    def test_under_budget_passes(self):
        limiter = ThroughputLimiter(max_attempts=3, window_seconds=60)
        assert limiter.check_and_record("k") is True
        assert limiter.check_and_record("k") is True
        assert limiter.check_and_record("k") is True

    def test_over_budget_rejected(self):
        limiter = ThroughputLimiter(max_attempts=3, window_seconds=60)
        for _ in range(3):
            limiter.check_and_record("k")
        assert limiter.check_and_record("k") is False
        # Still rejected after further attempts within window
        assert limiter.check_and_record("k") is False

    def test_keys_isolated(self):
        limiter = ThroughputLimiter(max_attempts=2, window_seconds=60)
        limiter.check_and_record("a")
        limiter.check_and_record("a")
        assert limiter.check_and_record("a") is False
        assert limiter.check_and_record("b") is True
