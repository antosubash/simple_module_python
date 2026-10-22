"""Permission primitives: the wildcard grant rule, the admin role and grant-source types."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection, Iterable
from typing import Any

PermissionSourceProvider = Callable[[], "Iterable[str] | Iterable[tuple[str, str]]"]
"""Sync callable returning permission keys, or ``(key, label)`` pairs."""

WILDCARD = "*"

ADMIN_ROLE = "admin"
"""The one role name the framework itself knows.

Everything else about roles is module-owned, but the framework needs this to
resolve the wildcard grant below and to decide who can still reach the app
while maintenance mode is on.
"""

# Default role→permission mapping. Admin gets all permissions via the wildcard.
# Additional mappings are added at registration time via PermissionRegistry.map_role.
DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    ADMIN_ROLE: [WILDCARD],
}


def is_admin(roles: list[str] | None) -> bool:
    """Whether ``roles`` carries the framework's admin role."""
    return bool(roles) and ADMIN_ROLE in roles


def is_admin_principal(user: Any) -> bool:
    """Whether *user* may use the admin role's shortcuts — admin and not a token.

    A principal carrying ``scopes`` (an ``api_tokens`` credential) is capped
    at those scopes even when its owner is an admin, so every check that
    admits admins on the role alone must use this rather than
    :func:`is_admin`; otherwise an admin's ``feature_flags.view`` token would
    still open the Doctor page. Duck-typed: ``UserContext`` lives in the auth
    module, which framework code must not import.
    """
    if user is None or getattr(user, "scopes", None) is not None:
        return False
    return is_admin(getattr(user, "roles", None))


def grants(held: Collection[str], required: str) -> bool:
    """Whether a principal holding *held* satisfies *required*.

    One place for the wildcard rule, so code that gates something *inside* a
    response — a column, a label, a card — reads the grant the same way
    ``RequiresPermission`` reads it at the door. Two hand-rolled ``in`` checks
    are two chances to forget that ``admin`` holds ``*`` and nothing else.

    An empty *required* is satisfied by anything: callers use it to mean "no
    permission gates this", which is the default for a declaration that never
    named one.
    """
    if not required:
        return True
    return WILDCARD in held or required in held


GrantSource = Callable[[Any, Any], Awaitable[Collection[str]]]
"""``async (request, user) -> keys`` — permissions a principal holds beyond its roles.

How a module that stores grants of its own (``permissions``' per-user grants)
gets them into the one set every check reads, without the framework importing
it (SM009). Called once per authenticated request by
``simple_module_hosting.permissions.resolve_principal_permissions``, so a
source that reads the database must cache: it sits on the hot path of every
page load.
"""
