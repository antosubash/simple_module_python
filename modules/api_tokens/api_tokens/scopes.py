"""What a creator may put on a token: scopes they hold, roles that are safe.

A scope must be a registered permission the creator holds *right now*, so a
token can never be created wider than the person creating it. That is the
check at creation; the cap the token carries is then applied on every
request on top of the owner's live grants (``apply_scope_cap``), so a later
demotion shrinks the token without anyone touching it.
"""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import Request
from simple_module_core.permissions import WILDCARD
from simple_module_core.tenancy import is_tenant_role
from simple_module_hosting.permissions import ensure_resolved_permissions

from api_tokens.constants import FORBIDDEN_SERVICE_ROLES
from api_tokens.service import TokenError


def _registry(request: Request):
    return request.app.state.sm.permissions


async def assignable_scopes(request: Request) -> list[str]:
    """Every registered permission the current principal holds, wildcard expanded."""
    registered = _registry(request).all_permissions
    held = await ensure_resolved_permissions(request)
    if WILDCARD in held:
        return sorted(p for p in registered if p != WILDCARD)
    return sorted(p for p in registered if p in held and p != WILDCARD)


def assignable_roles(request: Request) -> list[str]:
    """Platform roles a service key may carry: never ``admin``, never ``tenant:*``.

    Tenant roles come from a membership, which a service key does not have.
    """
    return sorted(
        role
        for role in _registry(request).role_map
        if role not in FORBIDDEN_SERVICE_ROLES and not is_tenant_role(role)
    )


def check_subset(requested: Iterable[str], allowed: Iterable[str], error_key: str) -> list[str]:
    """``requested`` deduplicated and sorted, or :class:`TokenError` naming the first stray."""
    allowed_set = set(allowed)
    wanted = sorted(set(requested))
    for item in wanted:
        if item not in allowed_set:
            raise TokenError(error_key, value=item)
    return wanted


__all__ = ["assignable_roles", "assignable_scopes", "check_subset"]
