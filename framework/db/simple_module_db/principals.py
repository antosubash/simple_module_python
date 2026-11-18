"""Build a live resource principal in the caller's async database session."""

from __future__ import annotations

from copy import copy
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from simple_module_core.permissions import WILDCARD
from simple_module_core.principal_permissions import load_principal
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
    """The live account principal, or None for an unusable account/tenant.

    Requires a web/worker-configured async session. Does not commit, change the
    ambient tenant, authenticate a token, or leave resource queries tenant-bound.
    A platform wildcard bypasses membership, but still requires an active tenant.
    """
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
    elif tenant_id is None:
        return None
    if tenant_id is not None and not is_valid_tenant_id(tenant_id):
        return None
    # Autoflush must never stamp pending writes with the lookup tenant.
    await session.flush()
    with tenant_context(tenant_id) if tenant_id is not None else no_tenant():
        found = await registry.directory.get_many(session, [user_id], with_roles=True)
        account = found.get(user_id)
        if account is None or not account.is_active:
            return None
        # IdP claims exist only on authenticated requests, never an ID lookup.
        roles = [r for r in account.roles or () if not is_tenant_role(r)]
        role = None
        if registry.multi_tenant and tenant_id is not None:
            if registry.membership_role is None:
                return None
            role = await registry.membership_role(session, user_id, tenant_id)
            if role is not None:
                roles.append(tenant_role(role))
        user = SimpleNamespace(
            id=user_id, email=account.email, name=account.label, roles=roles, tenant_id=tenant_id
        )
        permissions = registry.permissions
        if registry.role_overlays is not None:
            # Never publish an uncommitted transaction's overlay to other sessions.
            permissions = copy(permissions)
            permissions.replace_role_overlays(await registry.role_overlays(session, roles))
        principal = await load_principal(None, user, permissions, db=session)
        if registry.multi_tenant and role is None:
            if principal is None or WILDCARD not in principal.permissions:
                return None
            if (
                tenant_id is None
                or registry.tenant_active is None
                or not await registry.tenant_active(session, tenant_id)
            ):
                return None
        return principal
