"""Shared account permission resolution for requests and headless principals."""

from __future__ import annotations

import logging
from typing import Any

from simple_module_core.permissions import (
    DEFAULT_ROLE_PERMISSIONS,
    WILDCARD,
    PermissionRegistry,
    grants,
)
from simple_module_core.tenancy import is_tenant_role

logger = logging.getLogger(__name__)


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


def _role_and_claimed(
    user: Any,
    role_map: dict[str, list[str]] | None,
    *,
    include_tenant_roles: bool = True,
) -> set[str]:
    """The role-derived set plus the principal's own ``permissions`` (GH #436).

    Read duck-typed (``UserContext.permissions`` lives in the auth module, which
    framework code must not import). The claimed keys never include the
    wildcard: like a grant source, a token or IdP claim cannot make an admin.
    """
    roles = getattr(user, "roles", None) or []
    if not include_tenant_roles:
        roles = [r for r in roles if not is_tenant_role(r)]
    permissions = resolve_permissions(roles, role_map=role_map)
    permissions.update(p for p in getattr(user, "permissions", None) or () if p != WILDCARD)
    return permissions


def apply_scope_cap(permissions: set[str], user: Any) -> set[str]:
    """Cap *permissions* at the principal's token scopes, if it carries any.

    ``scopes`` is ``None`` for an ordinary session: nothing to cap. A list —
    an API token's — is a ceiling: the result is what the principal holds
    *and* the token names. Holding the wildcard (an admin) expands it to the
    scope list, so an admin's token is worth exactly its scopes rather than
    everything. Applied on every request on top of the owner's *live* grants,
    so demoting the owner shrinks every token they hold at once.

    A ``*`` inside the scope list is ignored: a token can never carry the
    wildcard, whatever row it was built from. Read duck-typed — the
    ``UserContext`` field lives in the auth module (SM009).
    """
    scopes = getattr(user, "scopes", None)
    if scopes is None:
        return permissions
    allowed = {s for s in scopes if s and s != WILDCARD}
    if WILDCARD in permissions:
        return allowed
    return permissions & allowed


async def resolve_principal_permissions(
    request: Any,
    user: Any,
    registry: PermissionRegistry | None,
    *,
    include_tenant_roles: bool = True,
) -> set[str]:
    """Everything *user* holds: its roles' permissions plus every grant source.

    The one resolution both ``InertiaLayoutDataMiddleware`` and
    ``RequiresPermission`` use, so the door, the menu and the frontend cannot
    disagree about what a principal may do (GH #337).

    A source that raises contributes nothing — failing closed, a denied page
    rather than an unauthorised one — and is logged rather than turned into a
    500 on every request. A principal already holding the wildcard skips the
    sources: nothing they return could widen it, and a source may cost a read.
    A token principal's set is then capped at its scopes (:func:`apply_scope_cap`),
    and is empty when its account no longer holds the permission the
    credential requires (:func:`lacks_required_permission`).

    Global delegation checks exclude synthetic tenant roles with
    ``include_tenant_roles=False``. Credential validity remains tenant-aware;
    scope caps still apply, and the request's cached set is left untouched.
    """
    held = await _held_permissions(
        request, user, registry, include_tenant_roles=include_tenant_roles
    )
    credential_held = held
    # Credential validity stays tenant-aware; only resolve the rest when needed.
    if not include_tenant_roles and getattr(user, "required_permission", None):
        role_map = registry.role_map if registry is not None else None
        credential_held = held | resolve_permissions(getattr(user, "roles", None) or [], role_map)
    if lacks_required_permission(user, credential_held):
        return set()
    return apply_scope_cap(held, user)


async def _held_permissions(
    request: Any,
    user: Any,
    registry: PermissionRegistry | None,
    *,
    include_tenant_roles: bool = True,
    db: Any = None,
) -> set[str]:
    """What *user*'s account holds right now, before any scope cap."""
    role_map = registry.role_map if registry is not None else None
    permissions = _role_and_claimed(user, role_map, include_tenant_roles=include_tenant_roles)
    if registry is None or WILDCARD in permissions:
        return permissions
    for source in registry.grant_sources:
        try:
            # Grants are additive keys only: the wildcard (admin) comes from
            # roles, never from a source, so a stray ``*`` row can't escalate.
            session_source = registry.session_grant_source(source)
            if db is not None and session_source is not None:
                keys = await session_source(db, user)
            else:
                keys = await source(request, user)
            permissions.update(k for k in keys if k != WILDCARD)
        except Exception:
            logger.exception("Grant source %r raised; contributing nothing", source)
    return permissions


def lacks_required_permission(user: Any, held: set[str]) -> bool:
    """Whether *user*'s credential requires a permission its account lacks.

    A credential may name a permission its account must *currently* hold for
    it to authenticate at all (``required_permission``, read duck-typed — an
    ``api_tokens`` personal token requires ``api_tokens.use``). Checked
    against the uncapped, tenant-aware set, so revoking the permission from a
    role, a tenant role or a direct grant retires every such credential at once.
    """
    required = getattr(user, "required_permission", None)
    return bool(required) and not grants(held, required)
