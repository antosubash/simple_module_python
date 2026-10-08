"""Permission enforcement dependency for FastAPI endpoints."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, Request
from simple_module_core.permissions import DEFAULT_ROLE_PERMISSIONS, WILDCARD, grants

if TYPE_CHECKING:
    from simple_module_core.permissions import PermissionRegistry

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_ROLE_PERMISSIONS",
    "PERMISSION_DENIED_PREFIX",
    "WILDCARD",
    "RequiresPermission",
    "ensure_resolved_permissions",
    "expand_permissions",
    "resolve_permissions",
    "resolve_principal_permissions",
    "resolved_permissions_for",
]

# How a denial spells the missing permission in ``HTTPException.detail``.
# Exported because the error-page handler parses the name back out of it to
# tell the visitor what to ask an admin for; two copies of this literal in two
# files is exactly the drift that would leave the 403 page with no permission
# to name and no test to notice.
PERMISSION_DENIED_PREFIX = "Permission required: "


def resolve_permissions(
    roles: list[str],
    role_map: dict[str, list[str]] | None = None,
) -> set[str]:
    """Resolve a set of roles into a flat set of permission strings."""
    if role_map is None:
        role_map = DEFAULT_ROLE_PERMISSIONS
    permissions: set[str] = set()
    for role in roles:
        permissions.update(role_map.get(role, []))
    return permissions


async def resolve_principal_permissions(
    request: Request,
    user: Any,
    registry: PermissionRegistry | None,
) -> set[str]:
    """Everything *user* holds: its roles' permissions plus every grant source.

    The one resolution both ``InertiaLayoutDataMiddleware`` and
    ``RequiresPermission`` use, so the door, the menu and the frontend cannot
    disagree about what a principal may do (GH #337).

    A source that raises contributes nothing — failing closed, a denied page
    rather than an unauthorised one — and is logged rather than turned into a
    500 on every request. A principal already holding the wildcard skips the
    sources: nothing they return could widen it, and a source may cost a read.
    """
    role_map = registry.role_map if registry is not None else None
    permissions = resolve_permissions(getattr(user, "roles", []), role_map=role_map)
    if registry is None or WILDCARD in permissions:
        return permissions
    for source in registry.grant_sources:
        try:
            # Grants are additive keys only: the wildcard (admin) comes from
            # roles, never from a source, so a stray ``*`` row can't escalate.
            permissions.update(k for k in await source(request, user) if k != WILDCARD)
        except Exception:
            logger.exception("Grant source %r raised; contributing nothing", source)
    return permissions


def _registry_for(request: Request) -> PermissionRegistry | None:
    sm = getattr(getattr(request.app, "state", None), "sm", None)
    return getattr(sm, "permissions", None) if sm is not None else None


async def ensure_resolved_permissions(request: Request) -> set[str]:
    """:func:`resolved_permissions_for`, grant sources included on a cache miss.

    The middleware has normally resolved and cached the set already; this is
    the fallback for a bare router without it, which — unlike the synchronous
    reader — can await the grant sources.
    """
    cached: set[str] | None = getattr(request.state, "resolved_permissions", None)
    if cached is not None:
        return cached
    user = getattr(request.state, "user", None)
    if user is None:
        return set()
    permissions = await resolve_principal_permissions(request, user, _registry_for(request))
    request.state.resolved_permissions = permissions
    return permissions


def expand_permissions(
    resolved: set[str],
    all_permissions: list[str],
) -> list[str]:
    """Expand wildcard to the full permission list for frontend consumption."""
    if WILDCARD in resolved:
        return sorted(set(all_permissions))
    return sorted(resolved)


def resolved_permissions_for(request: Request) -> set[str]:
    """The permission set this request's principal holds, wildcard included.

    Prefers what ``InertiaLayoutDataMiddleware`` already resolved and cached on
    ``request.state``; falls back to resolving from the registry's role map when
    the middleware is not in the stack (a bare router under a test transport),
    caching the result so a route with several gates resolves once.

    Anonymous requests hold nothing. Exposed because a handler sometimes has to
    gate part of its *response* rather than the route — the audit log's entity
    labels, for one — and that decision must read the same permission set the
    door did.

    Includes every registered grant source (the ``permissions`` module's
    direct per-user grants) whenever the middleware or ``RequiresPermission``
    resolved first — which is always in a real app. Only the bare-router
    fallback below is role-derived, because it cannot await a source; a caller
    that may run there first should use :func:`ensure_resolved_permissions`.
    """
    cached: set[str] | None = getattr(request.state, "resolved_permissions", None)
    if cached is not None:
        return cached

    user = getattr(request.state, "user", None)
    if user is None:
        return set()

    perm_registry = _registry_for(request)
    role_map = perm_registry.role_map if perm_registry is not None else None
    permissions = resolve_permissions(user.roles, role_map=role_map)
    request.state.resolved_permissions = permissions
    return permissions


class RequiresPermission:
    """FastAPI dependency that enforces a specific permission.

    Honours roles *and* every registered grant source, so a direct per-user
    grant from the ``permissions`` module takes effect here too.

    Usage::

        @router.post("/", dependencies=[Depends(RequiresPermission("products.create"))])
        async def create_product(...):
            ...
    """

    def __init__(self, permission: str) -> None:
        self.permission = permission

    async def __call__(self, request: Request) -> None:
        user = getattr(request.state, "user", None)
        if user is None:
            raise HTTPException(status_code=401, detail="Authentication required")

        if not grants(await ensure_resolved_permissions(request), self.permission):
            raise HTTPException(
                status_code=403,
                detail=f"{PERMISSION_DENIED_PREFIX}{self.permission}",
            )
