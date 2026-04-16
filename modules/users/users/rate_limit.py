"""In-process rate limiters — TTL caches, no Redis.

Note: counters live in the worker process, so a multi-worker deployment (e.g.
``uvicorn --workers 4``) has independent counters per worker. Effective
thresholds scale with worker count. Swap for a Redis-backed store when you
deploy behind more than a single worker.
"""

from __future__ import annotations

from cachetools import TTLCache


class LoginRateLimiter:
    """Per-key failure counter with a cooldown window after N failures."""

    def __init__(
        self,
        max_failures: int = 5,
        window_seconds: int = 300,
        cooldown_seconds: int = 900,
    ) -> None:
        self._fails: TTLCache = TTLCache(maxsize=10_000, ttl=window_seconds)
        self._locks: TTLCache = TTLCache(maxsize=10_000, ttl=cooldown_seconds)
        self._max = max_failures

    def is_locked(self, key: str) -> bool:
        return key in self._locks

    def record_failure(self, key: str) -> None:
        count = self._fails.get(key, 0) + 1
        self._fails[key] = count
        if count >= self._max:
            self._locks[key] = True
            self._fails.pop(key, None)

    def reset(self, key: str) -> None:
        self._fails.pop(key, None)
        self._locks.pop(key, None)


class ThroughputLimiter:
    """N requests per rolling window per key — counts every attempt.

    Used to dampen enumeration and email-spam on endpoints like
    ``/forgot-password`` and ``/register`` where a failure-based lockout
    (``LoginRateLimiter``) isn't the right shape — the attacker is after the
    side-effect itself, not a correct credential.
    """

    def __init__(self, max_attempts: int = 10, window_seconds: int = 300) -> None:
        self._hits: TTLCache = TTLCache(maxsize=10_000, ttl=window_seconds)
        self._max = max_attempts

    def check_and_record(self, key: str) -> bool:
        """Return True if this attempt is within budget; False if throttled."""
        count = self._hits.get(key, 0) + 1
        self._hits[key] = count
        return count <= self._max
