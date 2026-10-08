"""Rate-limit primitives shared by the host's request guards.

Two pieces, both free of Starlette/Redis so any layer can use them:

* :func:`parse_rate` turns ``"120/minute"`` into a :class:`RateSpec`.
* :class:`InProcessWindowStore` is the fixed-window counter the host falls back
  to when no Redis is configured. Its counters live in one worker process, so a
  multi-worker deployment multiplies the effective limit by the worker count.

The Redis-backed store lives in ``simple_module_hosting`` (it owns the
connection); both implement :class:`WindowStore`.
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

__all__ = [
    "InProcessWindowStore",
    "RateLimitError",
    "RateSpec",
    "WindowResult",
    "WindowStore",
    "parse_rate",
]

_PERIODS = {
    "second": 1,
    "sec": 1,
    "s": 1,
    "minute": 60,
    "min": 60,
    "m": 60,
    "hour": 3600,
    "h": 3600,
    "day": 86400,
    "d": 86400,
}
_RATE_RE = re.compile(r"^\s*(\d+)\s*/\s*(?:(\d+)\s*)?([a-z]+?)s?\s*$", re.IGNORECASE)
_OFF_WORDS = frozenset({"", "off", "none", "false", "disabled", "0"})


class RateLimitError(ValueError):
    """A rate string that is not ``<count>/<period>``."""


@dataclass(frozen=True, slots=True)
class RateSpec:
    """``limit`` requests per ``period`` seconds (fixed window)."""

    limit: int
    period: int

    def __str__(self) -> str:
        return f"{self.limit}/{self.period}s"


def parse_rate(value: str | None) -> RateSpec | None:
    """Parse ``"120/minute"`` / ``"5/10s"`` / ``"1000/hour"``.

    Returns ``None`` for a disabled limit (blank, ``off``, ``none``, ``0``).
    Raises :class:`RateLimitError` for anything else that does not parse, so a
    typo fails loudly at boot instead of silently disabling protection.
    """
    if value is None or value.strip().lower() in _OFF_WORDS:
        return None
    match = _RATE_RE.match(value)
    if match is None:
        raise RateLimitError(f"invalid rate {value!r}; expected '<count>/<second|minute|hour|day>'")
    count, multiple, unit = int(match.group(1)), match.group(2), match.group(3).lower()
    seconds = _PERIODS.get(unit)
    if seconds is None:
        raise RateLimitError(f"invalid rate {value!r}: unknown period {unit!r}")
    if count <= 0:
        return None
    return RateSpec(limit=count, period=seconds * (int(multiple) if multiple else 1))


@dataclass(frozen=True, slots=True)
class WindowResult:
    allowed: bool
    #: Seconds until the current window ends (the ``Retry-After`` value).
    retry_after: int
    count: int


class WindowStore(Protocol):
    async def hit(self, key: str, spec: RateSpec) -> WindowResult:
        """Count one request against *key* and report whether it is within budget."""
        ...


class InProcessWindowStore:
    """Per-process fixed-window counters. Not shared between workers."""

    _MAX_KEYS = 50_000

    def __init__(self, *, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._windows: dict[str, tuple[int, int]] = {}  # key -> (window_end_ms, count)

    async def hit(self, key: str, spec: RateSpec) -> WindowResult:
        now = self._clock()
        entry = self._windows.get(key)
        if entry is None or entry[0] <= now * 1000:
            if len(self._windows) >= self._MAX_KEYS:
                self._sweep(now)
            entry = (int(now * 1000) + spec.period * 1000, 0)
        end_ms, count = entry
        count += 1
        self._windows[key] = (end_ms, count)
        retry = max(1, math.ceil(end_ms / 1000 - now))
        return WindowResult(allowed=count <= spec.limit, retry_after=retry, count=count)

    def _sweep(self, now: float) -> None:
        now_ms = now * 1000
        self._windows = {k: v for k, v in self._windows.items() if v[0] > now_ms}
        if len(self._windows) >= self._MAX_KEYS:
            # Everything is live: shed the oldest half rather than grow unbounded.
            keep = sorted(self._windows.items(), key=lambda kv: kv[1][0], reverse=True)
            self._windows = dict(keep[: self._MAX_KEYS // 2])
