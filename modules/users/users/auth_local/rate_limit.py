"""In-process rate limiters — TTL caches, no Redis.

Note: counters live in the worker process, so a multi-worker deployment (e.g.
``uvicorn --workers 4``) has independent counters per worker. Effective
thresholds scale with worker count. Swap for a Redis-backed store when you
deploy behind more than a single worker.
"""

from __future__ import annotations

from cachetools import TTLCache
from fastapi import HTTPException, Request, status


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


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def enforce_auth_throughput_limit(request: Request) -> None:
    """FastAPI dependency that rejects the request with 429 when this IP has
    exhausted its attempts budget on shared auth side-effect endpoints.

    Applied to forgot-password / register / accept-invite / request-verify-token,
    which otherwise allow unlimited email or account-creation spam, and to
    ``/me/password``, where a wrong current password is free to guess.

    Lives here rather than beside the endpoints it guards because
    ``self_account`` needs it too and ``api`` already imports *that* module —
    the dependency has to sit below both, not beside one of them.
    """
    limiter: ThroughputLimiter = request.app.state.users.auth_throughput_limiter
    key = f"{request.url.path}::{_client_ip(request)}"
    if not limiter.check_and_record(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts — try again later",
        )
