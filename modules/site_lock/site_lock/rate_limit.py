"""In-memory per-IP attempt limiter for the unlock endpoint.

Deliberately process-local: adequate for the single-process staging
deployments this module targets. The ``users`` login lockout is not reused
because importing it would couple ``site_lock`` to the ``users`` module, and the
site lock must also work under the ``keycloak`` provider.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class _Bucket:
    failures: list[float] = field(default_factory=list)
    blocked_until: float = 0.0


class AttemptLimiter:
    """Track failed unlock attempts per client key and impose a cooldown."""

    def __init__(
        self,
        *,
        max_failures: int,
        window_seconds: int,
        cooldown_seconds: int,
    ) -> None:
        self._max = max_failures
        self._window = window_seconds
        self._cooldown = cooldown_seconds
        self._buckets: dict[str, _Bucket] = {}
        self._next_sweep = 0.0

    @staticmethod
    def _now(now: float | None) -> float:
        return time.monotonic() if now is None else now

    def _sweep(self, moment: float) -> None:
        if moment < self._next_sweep:
            return
        self._buckets = {
            key: bucket
            for key, bucket in self._buckets.items()
            if bucket.blocked_until > moment
            or (bucket.failures and moment - bucket.failures[-1] < self._window)
        }
        self._next_sweep = moment + self._window

    def is_blocked(self, key: str, *, now: float | None = None) -> bool:
        moment = self._now(now)
        self._sweep(moment)
        bucket = self._buckets.get(key)
        return bucket is not None and bucket.blocked_until > moment

    def record_failure(self, key: str, *, now: float | None = None) -> None:
        moment = self._now(now)
        self._sweep(moment)
        bucket = self._buckets.setdefault(key, _Bucket())
        bucket.failures = [t for t in bucket.failures if moment - t < self._window]
        bucket.failures.append(moment)
        if len(bucket.failures) >= self._max:
            bucket.blocked_until = moment + self._cooldown
            bucket.failures.clear()

    def reset(self, key: str) -> None:
        self._buckets.pop(key, None)


__all__ = ["AttemptLimiter"]
