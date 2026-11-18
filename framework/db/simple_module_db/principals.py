"""Build a live resource principal in the caller's async database session."""

from __future__ import annotations

from copy import copy
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from simple_module_core.principal_permissions import (
    _held_permissions,
    apply_scope_cap,
    lacks_required_permission,
)
from simple_module_core.principals import PRINCIPALS_KEY, PrincipalRegistry
from simple_module_core.resources import ResourcePrincipal
from simple_module_core.tenancy import is_tenant_role, tenant_role

from simple_module_db.tenancy import is_valid_tenant_id, no_tenant, tenant_context


def bind_principal_registry(factory: Any, registry: PrincipalRegistry) -> None:
    """Bind to this factory only; preserve its transaction/session metadata."""
    factory.configure(info={**factory.kw.get("info", {}), PRINCIPALS_KEY: registry})


async def principal_for(
    session: Any, user_id: str, tenant_id: str | None
) -> ResourcePrincipal | None:
    """The live account principal, or None for an unusable account/membership.

    Requires a web/worker-configured async session. Does not commit, change the
    ambient tenant, authenticate a token, or leave resource queries tenant-bound.
    """
    return await _principal_for(session, user_id, tenant_id)


async def _principal_for(
    session: Any, user_id: str, tenant_id: str | None, *, request: Any = None
) -> ResourcePrincipal | None:
    registry: PrincipalRegistry | None = session.info.get(PRINCIPALS_KEY)
    if registry is None:
        raise RuntimeError("No principal registry bound to this session factory")
    try:
        user_id = str(UUID(str(user_id)))
    except ValueError:
        user_id = str(user_id)
    if not registry.multi_tenant:
        # A single-tenant request cannot select an arbitrary tenant either.
        tenant_id = registry.default_tenant
    elif tenant_id is None and request is None:
        return None
    if tenant_id is not None and not is_valid_tenant_id(tenant_id):
        return None
    with tenant_context(tenant_id) if tenant_id is not None else no_tenant():
        authenticated = getattr(request.state, "user", None) if request is not None else None
        # Service credentials represent no directory user or tenant membership.
        service = getattr(authenticated, "auth_kind", None) == "service"
        found = await registry.directory.get_many(session, [user_id], with_roles=True)
        account = found.get(user_id)
        if not service and (account is None or not account.is_active):
            return None
        roles = account.roles if account is not None else None
        if roles is None:
            # IdP claims exist only on an authenticated request, never an id lookup.
            roles = getattr(authenticated, "roles", None) or ()
        roles = [r for r in roles if not is_tenant_role(r)]
        if registry.multi_tenant and tenant_id is not None and not service:
            if registry.membership_role is None:
                return None
            role = await registry.membership_role(session, user_id, tenant_id)
            if role is None:
                return None
            roles.append(tenant_role(role))
        user = (
            copy(authenticated)
            if authenticated is not None
            else SimpleNamespace(id=user_id, email=account.email, name=account.label)
        )
        user.id, user.roles, user.tenant_id = user_id, roles, tenant_id
        permissions = registry.permissions
        if registry.role_overlays is not None:
            # Never publish an uncommitted transaction's overlay to other sessions.
            permissions = copy(permissions)
            permissions.replace_role_overlays(await registry.role_overlays(session, roles))
        held = await _held_permissions(request, user, permissions, db=session)
        if lacks_required_permission(user, held):
            return None
        if request is not None:
            request.state.user = user
        return ResourcePrincipal(
            user_id=user_id, permissions=frozenset(apply_scope_cap(held, user))
        )
