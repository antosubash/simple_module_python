"""The ``tenant`` shared Inertia prop: active tenant + the user's memberships.

Providers are synchronous, so this reads the resolver's cache only — the
resolver has always populated it earlier in the same request.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request

from tenants.resolver import cached_memberships


def tenant_shared_props(request: Request) -> dict[str, Any]:
    user = getattr(request.state, "user", None)
    if user is None:
        return {}
    memberships = cached_memberships(str(user.id)) or []
    active_id = getattr(request.state, "tenant_id", None)
    active = next((m for m in memberships if m.id == active_id), None)
    return {
        "tenant": {
            "active": active.model_dump(mode="json") if active else None,
            "memberships": [m.model_dump(mode="json") for m in memberships],
            "suspended": bool(getattr(request.state, "tenant_suspended", False)),
        }
    }
