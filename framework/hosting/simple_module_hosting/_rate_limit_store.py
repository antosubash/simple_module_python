"""Window stores behind the rate limiter: Redis when configured, else per-process."""

from __future__ import annotations

import logging
import time
from typing import Any

from simple_module_core.rate_limit import (
    InProcessWindowStore,
    RateSpec,
    WindowResult,
    WindowStore,
)

logger = logging.getLogger("simple_module.request_guard")

_KEY_PREFIX = "sm:rl:"
# Re-warn about a dead Redis at most this often, not once per request.
_WARN_EVERY = 60.0
# After a Redis error, skip Redis entirely for this long. Without it a blackholed
# Redis costs every anonymous request the full socket timeout.
_BACKOFF = 5.0

_LUA = """
local c = redis.call('INCR', KEYS[1])
local t = redis.call('PTTL', KEYS[1])
-- t < 0 heals a counter that somehow lost its TTL, which would block that IP forever.
-- ARGV[2] == '1' is a sliding window: every hit restarts it.
if c == 1 or t < 0 or ARGV[2] == '1' then
  redis.call('PEXPIRE', KEYS[1], ARGV[1])
  t = tonumber(ARGV[1])
end
return {c, t}
"""

_RESET_LUA = "redis.call('DEL', KEYS[1]) return 0"

# Read-only twin of ``_LUA``: a missing key is an empty window.
_PEEK_LUA = """
local c = redis.call('GET', KEYS[1])
if not c then return {0, 0} end
return {tonumber(c), redis.call('PTTL', KEYS[1])}
"""


def _parse(reply: Any, empty_retry: int) -> tuple[int, int]:
    """``(count, retry_after)`` from a script's ``{count, pttl}`` reply.

    *empty_retry* is the answer when the key has no TTL left to report.
    """
    count, pttl = int(reply[0]), int(reply[1])
    retry = max(1, -(-pttl // 1000)) if pttl > 0 else empty_retry
    return count, retry


class RedisWindowStore:
    """Fixed-window counters in Redis; shared across workers and processes.

    Never takes requests down: on a Redis error the hit is counted in a per-process
    fallback store instead (bounded, weaker than the shared budget but not "no
    limit"), and Redis is re-probed after ``_BACKOFF`` seconds, so recovery is
    automatic and nothing latches.
    """

    def __init__(self, client: Any, *, clock=time.monotonic) -> None:
        self._client = client
        self._clock = clock
        self._last_warn = float("-inf")
        self._down_until = float("-inf")
        self._fallback = InProcessWindowStore()

    @classmethod
    def from_url(cls, url: str) -> RedisWindowStore:
        import redis.asyncio as aioredis

        # Short timeouts: this is on the request path, and redis-py defaults to
        # none, so a Redis that accepts connections but stalls would hang us.
        client = aioredis.from_url(url, socket_connect_timeout=0.5, socket_timeout=0.5)
        return cls(client)

    async def _eval(self, script: str, key: str, *args: Any) -> Any:
        """Run *script* on *key*; ``None`` means "answer from the per-worker fallback"."""
        if self._clock() < self._down_until:
            return None
        try:
            return await self._client.eval(script, 1, _KEY_PREFIX + key, *args)
        except Exception as exc:
            now = self._clock()
            self._down_until = now + _BACKOFF
            if now - self._last_warn >= _WARN_EVERY:
                self._last_warn = now
                logger.warning(
                    "Rate limiter Redis unavailable (%s); using per-worker counters", exc
                )
            return None

    async def hit(self, key: str, spec: RateSpec, *, sliding: bool = False) -> WindowResult:
        args = (spec.period * 1000, "1") if sliding else (spec.period * 1000,)
        reply = await self._eval(_LUA, key, *args)
        if reply is None:
            return await self._fallback.hit(key, spec, sliding=sliding)
        count, retry = _parse(reply, spec.period)
        return WindowResult(allowed=count <= spec.limit, retry_after=retry, count=count)

    async def peek(self, key: str, spec: RateSpec) -> WindowResult:
        reply = await self._eval(_PEEK_LUA, key)
        if reply is None:
            return await self._fallback.peek(key, spec)
        count, retry = _parse(reply, 0)
        return WindowResult(allowed=count < spec.limit, retry_after=retry, count=count)

    async def reset(self, key: str) -> None:
        # The fallback too: hits taken during an outage live there.
        await self._fallback.reset(key)
        await self._eval(_RESET_LUA, key)


def build_store(redis_url: str | None) -> WindowStore:
    """Redis when configured and importable, else per-process counters."""
    if redis_url:
        try:
            return RedisWindowStore.from_url(redis_url)
        except Exception as exc:  # missing redis package, malformed URL
            logger.warning("Rate limiter cannot use Redis (%s); using per-worker counters", exc)
    return InProcessWindowStore()
