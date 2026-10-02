"""Who may address which settings scope on a multi-tenant host (GH #368).

``settings.view``/``.edit``/``.delete`` say what a caller may do to settings;
they say nothing about *whose* settings. On a multi-tenant host that left any
holder free to write the host-wide system scope — where every module's
DB-backed configuration lives — and any tenant's or user's scope by naming it
in the URL.

So on such a host:

- a caller's **own** tenant scope (the request's tenant) and **own** user scope
  need only the route's usual permission;
- everything else — the system scope, another tenant's or user's scope, and
  the admin tooling that spans scopes — needs a *platform settings admin*.

A platform settings admin holds ``settings.system``. On hosts with a resolver
(the ``tenants`` module), the request's tenant is a choice the user made and
tenant roles arrive as ``tenant:<role>``; global ``admin`` stays a platform
role even while working inside an organisation. On hosts without a resolver,
any legacy tenant-bound identity is not a platform admin either. New users no
longer carry a ``tenant_id`` column; tenancy is defined by memberships.

Single-tenant hosts are untouched: every check passes when ``multi_tenant`` is
off.
"""

from __future__ import annotations

from fastapi import HTTPException, Query, Request
from simple_module_core.permissions import grants
from simple_module_hosting.permissions import PERMISSION_DENIED_PREFIX, resolved_permissions_for

from settings.constants import PERM_SYSTEM, QP_SCOPE, QP_SCOPE_ID, QP_TENANT_ID, QP_USER_ID
from settings.contracts.schemas import SettingScope

_STATUS_FORBIDDEN = 403


def _multi_tenant(request: Request) -> bool:
    sm = getattr(request.app.state, "sm", None)
    return bool(getattr(getattr(sm, "settings", None), "multi_tenant", False))


def is_platform_settings_admin(request: Request) -> bool:
    """Whether the caller may address every settings scope."""
    if not _multi_tenant(request):
        return True
    if not grants(resolved_permissions_for(request), PERM_SYSTEM):
        return False
    if getattr(request.app.state, "tenant_resolver", None) is not None:
        return True
    user = getattr(request.state, "user", None)
    return getattr(user, "tenant_id", None) is None


def _own_tenant(request: Request) -> str | None:
    return getattr(request.state, "tenant_id", None)


def _own_user(request: Request) -> str | None:
    user = getattr(request.state, "user", None)
    user_id = getattr(user, "id", None)
    return str(user_id) if user_id is not None else None


def _deny() -> HTTPException:
    return HTTPException(
        status_code=_STATUS_FORBIDDEN, detail=f"{PERMISSION_DENIED_PREFIX}{PERM_SYSTEM}"
    )


def _require_own(request: Request, owned: str | None, scope_id: str | None) -> None:
    """Pass when *scope_id* is absent or the caller's own; else need platform."""
    if scope_id is None or (owned is not None and scope_id == owned):
        return
    if not is_platform_settings_admin(request):
        raise _deny()


def require_platform(request: Request) -> None:
    """Dependency: the route spans scopes or touches the system scope."""
    if not is_platform_settings_admin(request):
        raise _deny()


def require_own_tenant(request: Request, scope_id: str) -> None:
    """Dependency for ``/tenant/{scope_id}/…``."""
    _require_own(request, _own_tenant(request), scope_id)


def require_own_user(request: Request, scope_id: str) -> None:
    """Dependency for ``/user/{scope_id}/…``."""
    _require_own(request, _own_user(request), scope_id)


def require_resolvable(
    request: Request,
    user_id: str | None = Query(default=None, alias=QP_USER_ID),
    tenant_id: str | None = Query(default=None, alias=QP_TENANT_ID),
) -> None:
    """Dependency for ``/resolve/{key}``: only the caller's own chain.

    The chain ends at the system scope, so a caller resolving its own keys
    reads system values it may not address directly — by design: that is the
    effective configuration it already runs under, and secrets stay masked.
    """
    _require_own(request, _own_tenant(request), tenant_id)
    _require_own(request, _own_user(request), user_id)


def require_listable(
    request: Request,
    scope: SettingScope | None = Query(default=None, alias=QP_SCOPE),
    scope_id: str | None = Query(default=None, alias=QP_SCOPE_ID),
) -> None:
    """Dependency for the list route: one of the caller's own scopes, or platform."""
    if scope == SettingScope.TENANT and scope_id is not None:
        _require_own(request, _own_tenant(request), scope_id)
    elif scope == SettingScope.USER and scope_id is not None:
        _require_own(request, _own_user(request), scope_id)
    else:
        require_platform(request)


__all__ = [
    "is_platform_settings_admin",
    "require_listable",
    "require_own_tenant",
    "require_own_user",
    "require_platform",
    "require_resolvable",
]
