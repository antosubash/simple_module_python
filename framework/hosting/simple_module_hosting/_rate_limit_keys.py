"""Who a rate-limit budget belongs to: key resolution and bucket names (#529).

Works on the ASGI ``scope`` so the middleware and the :func:`RateLimit` dependency
(``request.scope``) share one resolver. By the time either runs, ``AuthMiddleware``
has set ``state["user"]`` (an API-token principal already carries its owner's id, a
service key its own ``service:<id>``), ``TenantMiddleware`` has set
``state["tenant_id"]`` and ``ProxyHeaders`` has rewritten ``scope["client"]``.
"""

from __future__ import annotations

from collections.abc import Iterable

from starlette.types import Scope

_UNKNOWN_IP = "unknown"
_ALL_METHODS = "*"
KEY_USER = "user"
KEY_IP = "ip"
KEY_USER_OR_IP = "user_or_ip"
KEY_TENANT = "tenant"


def client_ip(scope: Scope) -> str:
    client = scope.get("client")
    return client[0] if client else _UNKNOWN_IP


def _state(scope: Scope, name: str) -> object | None:
    return (scope.get("state") or {}).get(name)


def _user_id(scope: Scope) -> str | None:
    user = _state(scope, "user")
    uid = getattr(user, "id", None) if user is not None else None
    return None if uid is None or str(uid) == "" else str(uid)


def rule_key(scope: Scope, key: str) -> str:
    """``"<keykind>=<id>"`` for *key*; a missing user/tenant falls back to the IP.

    The tenant key applies to signed-in requests only. Anonymous traffic on a tenant
    subdomain resolves a tenant too, and sharing that bucket would let one anonymous
    client exhaust the whole tenant's budget, so it is counted per IP instead.
    """
    if key == KEY_TENANT:
        tenant = _state(scope, "tenant_id")
        if tenant and _user_id(scope) is not None:
            return f"{KEY_TENANT}={tenant}"
    elif key in (KEY_USER, KEY_USER_OR_IP):
        uid = _user_id(scope)
        if uid is not None:
            return f"{KEY_USER}={uid}"
    return f"{KEY_IP}={client_ip(scope)}"


def methods_label(methods: Iterable[str] | None) -> str:
    return ",".join(sorted(methods)) if methods else _ALL_METHODS


def rule_bucket(kind: str, pattern: str, methods: Iterable[str] | None) -> str:
    """``rule:<kind>:<methods>:<pattern>``; the key is appended by the caller.

    Methods are part of the bucket: two rules with one pattern but different verbs or
    rates must not share a counter (Redis fixes the window on the first hit).
    """
    return f"rule:{kind}:{methods_label(methods)}:{pattern}"
