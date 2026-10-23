"""Shared rate limiter for anonymous traffic to public routes (GH #347).

Pure ASGI; the public tiers are keyed on client IP. Sits *after* the auth middleware so it can tell
anonymous from signed-in requests, and after ``ProxyHeaders`` so
``SM_TRUSTED_PROXY`` is honoured (``scope["client"]`` is already rewritten).

Policy:

* rules from ``register_rate_limits`` (``app.state.rate_limit_rules``) apply first, to
  anonymous and signed-in requests alike, each keyed by its ``RateLimitRule.key``
  (``_rate_limit_keys``); the tiers below still apply afterwards;
* a request is limited by ``rate_limit_public`` only when the auth middleware judged
  it anonymous-allowed (``scope["state"]["auth_public"]``: framework defaults, the
  registry and the provider legacy paths; the shared public-access check if no auth middleware
  records a decision) **and** nobody is signed in. Health/static are never limited;
* a matching rule's own ``rate=`` replaces that default for the rule;
* ``rate_limit_authenticated`` (off by default) limits signed-in traffic, one budget per
  user (anonymous-or-id-less principals fall back to their IP);
* every other request is untouched.

Counting goes to Redis (``SM_REDIS_URL``, atomic Lua INCR + PEXPIRE) so all
workers share one budget; with no Redis, or while Redis is failing, it counts in
per-process counters — the limiter must never take requests down.
"""

from __future__ import annotations

import logging

from simple_module_core.app_state import get_public_routes, get_rate_limit_rules
from simple_module_core.rate_limit import (
    InProcessWindowStore,
    RateLimitRule,
    RateSpec,
    WindowStore,
    parse_rate,
)
from starlette.types import ASGIApp, Receive, Scope, Send

from simple_module_hosting._rate_limit_keys import KEY_IP, KEY_USER_OR_IP, rule_bucket, rule_key
from simple_module_hosting._request_guard_responses import send_guard_response
from simple_module_hosting.public_access import is_public

__all__ = ["RateLimitMiddleware"]

logger = logging.getLogger("simple_module.request_guard")

_MESSAGE = "Too many requests. Please slow down and try again shortly."
_OPERATIONAL_PREFIXES = ("/health", "/static/")


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

    def _policy(self, scope: Scope) -> tuple[str, RateSpec, str] | None:
        authed = scope.get("state", {}).get("user") is not None
        if authed:
            if self.authenticated_rate is None:
                return None
            return "auth", self.authenticated_rate, KEY_USER_OR_IP
        registry = get_public_routes(scope["app"])
        rule = registry.match(scope["method"], scope["path"]) if registry is not None else None
        flag = scope.get("state", {}).get("auth_public")
        if flag is None:  # no auth middleware recorded a decision
            flag = is_public(scope["app"], scope["method"], scope["path"])
        if not flag:
            return None
        if rule is None and scope["path"].startswith(_OPERATIONAL_PREFIXES):
            return None  # health probes and static assets are not an API surface
        if rule is not None and rule.rate is not None:
            spec = rule.rate_spec
            # Own namespace: a registry rule on the same pattern must not share
            # this counter (one request would count twice, periods would mix).
            bucket = f"public:{rule_bucket(rule.kind, rule.pattern, rule.methods)}"
            return (bucket, spec, KEY_IP) if spec is not None else None
        if self.public_rate is None:
            return None
        return "public", self.public_rate, KEY_IP

    def _rule(self, scope: Scope) -> tuple[str, RateLimitRule] | None:
        registry = get_rate_limit_rules(scope["app"])
        found = registry.match_entry(scope["method"], scope["path"]) if registry else None
        if found is None:
            return None
        kind, pattern, rule = found
        return rule_bucket(kind, pattern, rule.methods), rule

    async def _admit(self, scope: Scope, bucket: str, spec: RateSpec, key_kind: str):
        """Count one hit; ``None`` when allowed, else the 429 inputs."""
        key = rule_key(scope, key_kind)
        result = await self.store.hit(f"{bucket}:{key}", spec)
        if result.allowed:
            return None
        logger.warning(
            "Rate limit exceeded: %s %s %s bucket=%s limit=%s",
            scope["method"],
            scope["path"],
            key,
            bucket,
            spec,
        )
        return result.retry_after

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        checks: list[tuple[str, RateSpec, str]] = []
        matched = self._rule(scope)
        if matched is not None:
            bucket, rule = matched
            spec = parse_rate(rule.rate)
            if spec is not None:
                checks.append((bucket, spec, rule.key))
        policy = self._policy(scope)
        if policy is not None:
            checks.append(policy)
        for bucket, spec, key_kind in checks:
            retry_after = await self._admit(scope, bucket, spec, key_kind)
            if retry_after is not None:
                await send_guard_response(
                    scope,
                    receive,
                    send,
                    429,
                    _MESSAGE,
                    headers={"Retry-After": str(retry_after)},
                    extra={"retry_after": retry_after},
                )
                return
        await self.app(scope, receive, send)
