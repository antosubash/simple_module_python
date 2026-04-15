"""In-process login rate limiter — TTL caches, no Redis."""

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
