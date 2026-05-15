"""Tests for LoginRateLimiter and ThroughputLimiter."""

from __future__ import annotations

import pytest
from users.auth_local.rate_limit import LoginRateLimiter, ThroughputLimiter


@pytest.fixture
def limiter():
    """A limiter with max 5 failures, very short TTLs for fast tests."""
    return LoginRateLimiter(max_failures=5, window_seconds=60, cooldown_seconds=900)


class TestIsLocked:
    def test_not_locked_initially(self, limiter):
        assert limiter.is_locked("user@example.com::1.2.3.4") is False

    def test_not_locked_after_four_failures(self, limiter):
        key = "user@example.com::1.2.3.4"
        for _ in range(4):
            limiter.record_failure(key)
        assert limiter.is_locked(key) is False

    def test_locked_after_five_failures(self, limiter):
        key = "user@example.com::1.2.3.4"
        for _ in range(5):
            limiter.record_failure(key)
        assert limiter.is_locked(key) is True

    def test_sixth_request_still_locked(self, limiter):
        """Once locked, subsequent calls don't unlock."""
        key = "user@example.com::1.2.3.4"
        for _ in range(6):
            limiter.record_failure(key)
        assert limiter.is_locked(key) is True


class TestRecordFailure:
    def test_failure_counter_increments(self, limiter):
        key = "a::1"
        limiter.record_failure(key)
        limiter.record_failure(key)
        # Not locked after 2 failures (max is 5)
        assert limiter.is_locked(key) is False

    def test_reaching_max_clears_fail_counter(self, limiter):
        """After locking, the failure counter is removed (lock handles timeout)."""
        key = "a::1"
        for _ in range(5):
            limiter.record_failure(key)
        # Lock bucket holds the lock; fail bucket is cleared
        assert limiter.is_locked(key) is True
        # Further record_failure on a locked key doesn't raise
        limiter.record_failure(key)
        assert limiter.is_locked(key) is True


class TestReset:
    def test_reset_clears_failure_count(self, limiter):
        key = "b::2"
        for _ in range(4):
            limiter.record_failure(key)
        limiter.reset(key)
        # After reset, another 4 failures should NOT lock
        for _ in range(4):
            limiter.record_failure(key)
        assert limiter.is_locked(key) is False

    def test_reset_clears_lock(self, limiter):
        key = "b::2"
        for _ in range(5):
            limiter.record_failure(key)
        assert limiter.is_locked(key) is True
        limiter.reset(key)
        assert limiter.is_locked(key) is False

    def test_reset_on_unknown_key_does_not_raise(self, limiter):
        limiter.reset("never-seen-key::0.0.0.0")

    def test_successful_login_resets_counter(self, limiter):
        """Simulates a successful login after some failures resetting state."""
        key = "c::3"
        for _ in range(3):
            limiter.record_failure(key)
        # Successful login → reset
        limiter.reset(key)
        # Now 5 fresh failures should lock
        for _ in range(5):
            limiter.record_failure(key)
        assert limiter.is_locked(key) is True


class TestPerKeyIsolation:
    def test_different_keys_independent(self, limiter):
        key1 = "alice@example.com::1.1.1.1"
        key2 = "bob@example.com::2.2.2.2"
        for _ in range(5):
            limiter.record_failure(key1)
        assert limiter.is_locked(key1) is True
        assert limiter.is_locked(key2) is False

    def test_same_email_different_ip_independent(self, limiter):
        key1 = "user@example.com::1.1.1.1"
        key2 = "user@example.com::2.2.2.2"
        for _ in range(5):
            limiter.record_failure(key1)
        assert limiter.is_locked(key1) is True
        assert limiter.is_locked(key2) is False


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
