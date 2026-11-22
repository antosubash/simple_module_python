"""Permission enforcement dependency for FastAPI endpoints."""

from __future__ import annotations

from copy import copy
from dataclasses import replace
from typing import TYPE_CHECKING

from fastapi import HTTPException, Request
from simple_module_core.access.permission_denied import PERMISSION_DENIED_PREFIX, PermissionDenied
from simple_module_core.access.permissions import DEFAULT_ROLE_PERMISSIONS, WILDCARD, grants
from simple_module_core.access.principal_permissions import (
    _role_and_claimed,
    apply_scope_cap,
    lacks_required_permission,
    load_principal,
    resolve_permissions,
    resolve_principal_permissions,
)
from simple_module_core.access.principals import PRINCIPALS_KEY
from simple_module_core.access.resources import ResourcePrincipal
from simple_module_core.access.tenancy import is_tenant_role, tenant_role
from simple_module_core.modules.app_state import get_services

from simple_module_hosting._anonymous import demote_to_anonymous
from simple_module_hosting.token_guard import GATE_PERMISSION

if TYPE_CHECKING:
    from simple_module_core.access.permissions import PermissionRegistry


__all__ = [
    "DEFAULT_ROLE_PERMISSIONS",
    "PERMISSION_DENIED_PREFIX",
    "WILDCARD",
    "PermissionDenied",
    "RequiresPermission",
    "apply_scope_cap",
    "ensure_resolved_permissions",
    "expand_permissions",
    "lacks_required_permission",
    "resolve_permissions",
    "resolve_principal_permissions",
    "resolve_request_permissions",
    "resolved_permissions_for",
]


async def resolve_request_permissions(
    request: Request, registry: PermissionRegistry | None
) -> set[str]:
    """Resolve and cache the permission set of the request's principal.

    A principal whose credential requires a permission its account no longer
    holds is not authenticated: it is demoted to the anonymous visitor, so a
    gated route answers ``401`` — the same as for a revoked credential.
    """
    user = getattr(request.state, "user", None)
    if user is None:
        request.state.resolved_permissions = set()
        return set()
    tenant_id = getattr(request.state, "tenant_id", None)
    if getattr(user, "tenant_id", None) != tenant_id:
        # Grant sources see the effective tenant without changing the auth context.
        user = copy(user)
        user.tenant_id = tenant_id
    principal = await load_principal(request, user, registry)
    if principal is None:
        await demote_to_anonymous(request)
        return set()
    permissions = set(principal.permissions)
    request.state.resource_principal = _resource_principal_for(request, principal)
    request.state.resolved_permissions = permissions
    return permissions


def _resource_principal_for(request: Request, principal: ResourcePrincipal) -> ResourcePrincipal:
    """Keep account authentication separate from authorization in this tenant."""
    factory = getattr(getattr(get_services(request.app), "db", None), "session_factory", None)
    builder = factory.kw.get("info", {}).get(PRINCIPALS_KEY) if factory is not None else None
    if builder is not None and builder.multi_tenant:
        user = getattr(request.state, "user", None)
        # Public subdomains bind a tenant even for nonmembers. Service keys have
        # no account membership; their pinned tenant is validated by the resolver.
        # Only an uncapped platform wildcard may bypass account membership.
        if not getattr(request.state, "tenant_id", None) or (
            getattr(request.state, "tenant_role", None) is None
            and getattr(user, "auth_kind", None) != "service"
            and WILDCARD not in principal.permissions
        ):
            return ResourcePrincipal(None)
    if builder is None:
        return principal
    tenant_id = principal.tenant_id if builder.multi_tenant else builder.default_tenant
    # Tenant roles are membership facts, never platform/identity-provider claims.
    roles = frozenset(r for r in principal.roles if not is_tenant_role(r))
    role = getattr(request.state, "tenant_role", None)
    if builder.multi_tenant and tenant_id and role is not None:
        roles |= {tenant_role(role)}
    if (
        principal.context is builder.resource_context
        and principal.tenant_id == tenant_id
        and principal.roles == roles
    ):
        return principal
    return replace(principal, context=builder.resource_context, tenant_id=tenant_id, roles=roles)


def _registry_for(request: Request) -> PermissionRegistry | None:
    sm = get_services(request.app)
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
    return await resolve_request_permissions(request, _registry_for(request))


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
    held = _role_and_claimed(user, role_map)
    permissions = set() if lacks_required_permission(user, held) else apply_scope_cap(held, user)
    request.state.resolved_permissions = permissions
    return permissions


class RequiresPermission:
    """FastAPI dependency that requires any one of the supplied permissions.

    Honours roles *and* every registered grant source, so a direct per-user
    grant from the ``permissions`` module takes effect here too.

    Usage::

        @router.post("/", dependencies=[Depends(RequiresPermission("products.create"))])
        async def create_product(...):
            ...
    """

    # Tells ``token_guard`` this route is permission-gated, so an API token
    # may reach it — capped at its scopes by the check below.
    __sm_token_gate__ = GATE_PERMISSION

    def __init__(self, permission: str, *alternatives: str) -> None:
        self.permission = permission
        self.permissions = (permission, *alternatives)

    async def __call__(self, request: Request) -> None:
        user = getattr(request.state, "user", None)
        if user is None:
            raise HTTPException(status_code=401, detail="Authentication required")

        permissions = await ensure_resolved_permissions(request)
        if getattr(request.state, "user", None) is None:  # demoted while resolving
            raise HTTPException(status_code=401, detail="Authentication required")
        if not any(grants(permissions, key) for key in self.permissions):
            raise PermissionDenied(", ".join(self.permissions))
