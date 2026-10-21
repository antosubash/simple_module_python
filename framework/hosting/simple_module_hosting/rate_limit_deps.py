"""``RateLimit("10/minute", key="user")``: a per-route limit as a FastAPI dependency (#529).

Counts in the host's shared store (``app.state.sm.rate_limit_store``: Redis when
``SM_REDIS_URL`` is set, else per worker) with the same key resolution as
``register_rate_limits`` rules. Use it where a limit belongs to one handler;
use the registry for a path or prefix.
"""

from __future__ import annotations

from fastapi import HTTPException, Request
from simple_module_core.rate_limit import RateKey, RateSpec, parse_rate

from simple_module_hosting._rate_limit_keys import KEY_USER_OR_IP, methods_label, rule_key
from simple_module_hosting.token_guard import effective_route

_TOO_MANY = 429
_DETAIL = "Too many requests. Please slow down and try again shortly."
_RETRY_AFTER = "Retry-After"

__all__ = ["RateLimit"]


class RateLimit:
    """Dependency raising 429 with ``Retry-After`` past *rate* per *key*."""

    def __init__(self, rate: str, *, key: RateKey = KEY_USER_OR_IP) -> None:
        spec: RateSpec | None = parse_rate(rate)
        if spec is None:
            raise ValueError("RateLimit needs a real rate, not a disabled one")
        self.rate = rate
        self.spec = spec
        self.key = key

    async def __call__(self, request: Request) -> None:
        route = effective_route(request.scope)  # carries the include prefix
        path = getattr(route, "path", None) or request.url.path
        bucket = f"dep:{methods_label([request.method])}:{path}:{self.rate}"
        store = request.app.state.sm.rate_limit_store
        result = await store.hit(f"{bucket}:{rule_key(request.scope, self.key)}", self.spec)
        if not result.allowed:
            raise HTTPException(
                status_code=_TOO_MANY,
                detail=_DETAIL,
                headers={_RETRY_AFTER: str(result.retry_after)},
            )
