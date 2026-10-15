"""The tenant an API-token request acts for: the one the token was created in.

``api_tokens`` stamps each token with the tenant that was active when it was
created and copies it onto the principal's ``tenant_id``. Both kinds are
pinned there — a header, a subdomain or a session preference never moves them:

* A **service key** has no person and no memberships; its tenant only has to
  still exist and be active.
* A **personal access token** acts for its owner, so the owner must also still
  be an active member of that tenant. When they are not (removed, or the
  tenant suspended), the request is **de-authenticated** rather than left
  signed in without a tenant: every route a token may reach is permission
  gated, so it answers 401, the same as for a revoked token.
"""

from __future__ import annotations

from typing import Any

from auth.contracts.tokens import AUTH_KIND_SERVICE
from simple_module_db import is_valid_tenant_id
from simple_module_db.listeners import current_user_id
from starlette.requests import Request

from tenants.constants import TenantStatus


async def pinned_token_tenant(request: Request, user: Any) -> str | None:
    """The token's own tenant, or ``None`` (and, for a PAT, no principal)."""
    tenant_id = getattr(user, "tenant_id", None)
    if getattr(user, "auth_kind", None) == AUTH_KIND_SERVICE:
        return await _service_tenant(request, tenant_id)
    return await _personal_tenant(request, user, tenant_id)


async def _service_tenant(request: Request, tenant_id: Any) -> str | None:
    """The service key's pinned tenant, while that tenant exists and is active."""
    if not is_valid_tenant_id(tenant_id):
        return None
    from tenants.models import Tenant

    async with request.app.state.sm.db.session_factory() as db:
        tenant = await db.get(Tenant, tenant_id)
    if tenant is None or tenant.status != TenantStatus.ACTIVE:
        request.state.tenant_suspended = tenant is not None
        return None
    return tenant_id


async def _personal_tenant(request: Request, user: Any, tenant_id: Any) -> str | None:
    from tenants.resolver import _enter, memberships_for

    own = None
    if is_valid_tenant_id(tenant_id):
        memberships = await memberships_for(request.app, str(user.id))
        own = next((m for m in memberships if m.id == tenant_id), None)
    if own is None or own.status != TenantStatus.ACTIVE:
        request.state.tenant_suspended = own is not None
        _forget_principal(request)
        return None
    return _enter(request, user, own)


def _forget_principal(request: Request) -> None:
    request.state.user = None
    request.state.resolved_permissions = set()
    current_user_id.set(None)


__all__ = ["pinned_token_tenant"]
