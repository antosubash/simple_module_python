"""Redis :class:`~simple_module_core.leases.LeaseBackend` (GH #539).

* A lease is ``SET key token NX PX ttl``; refresh and release are Lua scripts
  that compare the stored token first, so only the live owner can touch it —
  an expired key is simply gone.
* A semaphore is a sorted set of tokens scored by expiry in milliseconds of
  Redis' own ``TIME`` (never this process's clock); every attempt first drops
  members whose score has passed, then admits while ``ZCARD < slots``.
* ``INCR <key>:fence`` hands out the fencing token, inside the same script.

Unlike the rate limiter there is no per-process fallback: a lease that Redis
could not confirm must not be reported as held, so errors propagate.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

# Holder and fence-counter keys live under disjoint prefixes: a name is never
# parsed, so ``foo:fence`` cannot collide with the counter of ``foo``.
_HOLDER_PREFIX = "sm:lease:h:"
_FENCE_PREFIX = "sm:lease:f:"
_SEM_HOLDER_PREFIX = "sm:sem:h:"
_SEM_FENCE_PREFIX = "sm:sem:f:"

_ACQUIRE = """
if redis.call('SET', KEYS[1], ARGV[1], 'NX', 'PX', ARGV[2]) then
  return redis.call('INCR', KEYS[2])
end
if redis.call('GET', KEYS[1]) == ARGV[1] then
  redis.call('PEXPIRE', KEYS[1], ARGV[2])
  return redis.call('INCR', KEYS[2])
end
return 0
"""

_REFRESH = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('PEXPIRE', KEYS[1], ARGV[2])
end
return 0
"""

_RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""

# Shared prologue: Redis' clock in ms, expired members dropped.
_SEM_NOW = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
local function keep(ttl)
  if redis.call('PTTL', KEYS[1]) < ttl then redis.call('PEXPIRE', KEYS[1], ttl) end
end
"""

_SEM_ACQUIRE = (
    _SEM_NOW
    + """
local ttl = tonumber(ARGV[3])
if redis.call('ZSCORE', KEYS[1], ARGV[1])
   or redis.call('ZCARD', KEYS[1]) < tonumber(ARGV[2]) then
  redis.call('ZADD', KEYS[1], now + ttl, ARGV[1])
  keep(ttl)
  return redis.call('INCR', KEYS[2])
end
return 0
"""
)

_SEM_REFRESH = (
    _SEM_NOW
    + """
local ttl = tonumber(ARGV[2])
if not redis.call('ZSCORE', KEYS[1], ARGV[1]) then return 0 end
redis.call('ZADD', KEYS[1], 'XX', now + ttl, ARGV[1])
keep(ttl)
return 1
"""
)

_SEM_RELEASE = _SEM_NOW + "return redis.call('ZREM', KEYS[1], ARGV[1])"


def _ms(ttl: float) -> int:
    return max(1, int(ttl * 1000))


class RedisLeaseBackend:
    """Leases shared by every process on one Redis.

    redis-py's asyncio connections belong to the event loop (and process) that
    opened them, and a Celery worker may run each task under a fresh
    ``asyncio.run``; the client is therefore rebuilt per loop and per process.
    """

    def __init__(self, url: str, *, factory: Any = None) -> None:
        self._url = url
        self._factory = factory
        self._client: Any = None
        self._owner: tuple[int, int] | None = None

    def _redis(self) -> Any:
        owner = (os.getpid(), id(asyncio.get_running_loop()))
        if self._client is None or self._owner != owner:
            if self._factory is not None:
                self._client = self._factory()
            else:
                import redis.asyncio as aioredis

                self._client = aioredis.from_url(self._url)
            self._owner = owner
        return self._client

    async def _eval(self, script: str, keys: list[str], *args: Any) -> int:
        return int(await self._redis().eval(script, len(keys), *keys, *args))

    @staticmethod
    def _lease_keys(name: str) -> list[str]:
        return [_HOLDER_PREFIX + name, _FENCE_PREFIX + name]

    @staticmethod
    def _sem_keys(name: str) -> list[str]:
        return [_SEM_HOLDER_PREFIX + name, _SEM_FENCE_PREFIX + name]

    async def acquire(self, name: str, token: str, ttl: float) -> int | None:
        return await self._eval(_ACQUIRE, self._lease_keys(name), token, _ms(ttl)) or None

    async def refresh(self, name: str, token: str, ttl: float) -> bool:
        return bool(await self._eval(_REFRESH, self._lease_keys(name)[:1], token, _ms(ttl)))

    async def release(self, name: str, token: str) -> bool:
        return bool(await self._eval(_RELEASE, self._lease_keys(name)[:1], token))

    async def semaphore_acquire(self, name: str, token: str, slots: int, ttl: float) -> int | None:
        keys = self._sem_keys(name)
        return await self._eval(_SEM_ACQUIRE, keys, token, slots, _ms(ttl)) or None

    async def semaphore_refresh(self, name: str, token: str, ttl: float) -> bool:
        return bool(await self._eval(_SEM_REFRESH, self._sem_keys(name)[:1], token, _ms(ttl)))

    async def semaphore_release(self, name: str, token: str) -> bool:
        return bool(await self._eval(_SEM_RELEASE, self._sem_keys(name)[:1], token))
