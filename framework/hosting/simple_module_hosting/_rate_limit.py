"""Shared rate limiter for anonymous traffic to public routes (GH #347).

Pure ASGI, keyed on client IP. Sits *after* the auth middleware so it can tell
anonymous from signed-in requests, and after ``ProxyHeaders`` so
``SM_TRUSTED_PROXY`` is honoured (``scope["client"]`` is already rewritten).

Policy:

* a request is limited by ``rate_limit_public`` only when the auth middleware judged
  it anonymous-allowed (``scope["state"]["auth_public"]``: framework defaults, the
  registry and the provider legacy paths; the registry alone if no auth provider
  is installed) **and** nobody is signed in. Health/static are never limited;
* a matching rule's own ``rate=`` replaces that default for the rule;
* ``rate_limit_authenticated`` (off by default) limits signed-in traffic;
* every other request is untouched.

Counting goes to Redis (``SM_REDIS_URL``, atomic Lua INCR + PEXPIRE) so all
workers share one budget; with no Redis, or if Redis fails, it fails open to
per-process counters / no limit — the limiter must never take requests down.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from simple_module_core.rate_limit import (
    InProcessWindowStore,
    RateSpec,
    WindowResult,
    WindowStore,
    parse_rate,
)
from starlette.types import ASGIApp, Receive, Scope, Send

from simple_module_hosting._request_guard_responses import send_guard_response

logger = logging.getLogger("simple_module.request_guard")

_MESSAGE = "Too many requests. Please slow down and try again shortly."
_KEY_PREFIX = "sm:rl:"
_OPERATIONAL_PREFIXES = ("/health", "/static/")
# Re-warn about a dead Redis at most this often, not once per request.
_WARN_EVERY = 60.0

_LUA = """
local c = redis.call('INCR', KEYS[1])
if c == 1 then redis.call('PEXPIRE', KEYS[1], ARGV[1]) end
return {c, redis.call('PTTL', KEYS[1])}
"""


class RedisWindowStore:
    """Fixed-window counters in Redis; shared across workers and processes.

    Fails open: any Redis error is logged (rate-limited) and the request is
    allowed, so an outage degrades to "no limit" rather than "no site".
    """

    def __init__(self, client: Any, *, clock=time.monotonic) -> None:
        self._client = client
        self._clock = clock
        self._last_warn = float("-inf")

    @classmethod
    def from_url(cls, url: str) -> RedisWindowStore:
        import redis.asyncio as aioredis

        # Short timeouts: this is on the request path, and redis-py defaults to
        # none, so a Redis that accepts connections but stalls would hang us.
        client = aioredis.from_url(url, socket_connect_timeout=0.5, socket_timeout=0.5)
        return cls(client)

    async def hit(self, key: str, spec: RateSpec) -> WindowResult:
        try:
            count, pttl = await self._client.eval(_LUA, 1, _KEY_PREFIX + key, spec.period * 1000)
        except Exception as exc:
            now = self._clock()
            if now - self._last_warn >= _WARN_EVERY:
                self._last_warn = now
                logger.warning("Rate limiter Redis unavailable (%s); failing open", exc)
            return WindowResult(allowed=True, retry_after=0, count=0)
        retry = max(1, -(-int(pttl) // 1000)) if int(pttl) > 0 else spec.period
        return WindowResult(allowed=int(count) <= spec.limit, retry_after=retry, count=int(count))


def build_store(redis_url: str | None) -> WindowStore:
    """Redis when configured and importable, else per-process counters."""
    if redis_url:
        try:
            return RedisWindowStore.from_url(redis_url)
        except Exception as exc:  # missing redis package, malformed URL
            logger.warning("Rate limiter cannot use Redis (%s); using per-worker counters", exc)
    return InProcessWindowStore()


class RateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        public_rate: str | None,
        authenticated_rate: str | None = None,
        store: WindowStore | None = None,
    ) -> None:
        self.app = app
        self.public_rate = parse_rate(public_rate)
        self.authenticated_rate = parse_rate(authenticated_rate)
        self.store = store if store is not None else InProcessWindowStore()

    def _policy(self, scope: Scope) -> tuple[str, RateSpec] | None:
        authed = scope.get("state", {}).get("user") is not None
        if authed:
            if self.authenticated_rate is None:
                return None
            return "auth", self.authenticated_rate
        registry = getattr(scope["app"].state, "public_routes", None)
        rule = registry.match(scope["method"], scope["path"]) if registry is not None else None
        flag = scope.get("state", {}).get("auth_public")
        if flag is None:  # no auth provider recorded a decision: registry is the truth
            flag = rule is not None
        if not flag:
            return None
        if rule is None and scope["path"].startswith(_OPERATIONAL_PREFIXES):
            return None  # health probes and static assets are not an API surface
        if rule is not None and rule.rate is not None:
            spec = parse_rate(rule.rate)
            return (f"rule:{rule.kind}:{rule.pattern}", spec) if spec is not None else None
        if self.public_rate is None:
            return None
        return "public", self.public_rate

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        policy = self._policy(scope)
        if policy is None:
            await self.app(scope, receive, send)
            return
        bucket, spec = policy
        client = scope.get("client")
        ip = client[0] if client else "unknown"
        result = await self.store.hit(f"{bucket}:{ip}", spec)
        if result.allowed:
            await self.app(scope, receive, send)
            return
        cid = scope.get("state", {}).get("correlation_id", "")
        logger.warning(
            "Rate limit exceeded: %s %s ip=%s bucket=%s limit=%s correlation_id=%s",
            scope["method"],
            scope["path"],
            ip,
            bucket,
            spec,
            cid,
        )
        await send_guard_response(
            scope,
            receive,
            send,
            429,
            _MESSAGE,
            headers={"Retry-After": str(result.retry_after)},
            extra={"retry_after": result.retry_after},
        )
