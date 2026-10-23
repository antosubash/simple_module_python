"""Tenant-role vocabulary shared by every module (#380).

A tenant membership role (``owner`` / ``admin`` / ``member``) reaches the
request principal as ``tenant:<role>`` for the *active* tenant only, so a
tenant ``admin`` can never be mistaken for the platform ``admin`` role. The
``tenants`` module assigns these; any other module maps them onto its own
permissions without depending on ``tenants``::

    from simple_module_core.tenancy import TenantRole, tenant_role

    registry.map_role(tenant_role(TenantRole.MEMBER), ["files.view"])
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection
from enum import StrEnum
from typing import Any

from simple_module_core.app_state import get_tenant_exists, get_tenant_members

TENANT_ROLE_PREFIX = "tenant:"


class TenantRole(StrEnum):
    """A member's role within one tenant."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class TenancyMode(StrEnum):
    """Whether a host scopes requests to tenants (#418).

    ``SINGLE``: one tenant for every request: no ``TenantMiddleware``, or one
    pinned with ``fixed=``. ``MULTI``: ``multi_tenant`` is on and each request
    resolves its own.
    """

    SINGLE = "single"
    MULTI = "multi"


def tenant_role(name: str) -> str:
    """The effective principal role for membership role ``name``: ``tenant:<name>``.

    Raises ``ValueError`` for a name that is not a :class:`TenantRole`, so a
    typo in a ``map_role`` call fails at boot instead of granting nothing.
    """
    try:
        role = TenantRole(name)
    except ValueError:
        raise ValueError(
            f"unknown tenant role {name!r}; expected one of {list(TenantRole)}"
        ) from None
    return f"{TENANT_ROLE_PREFIX}{role.value}"


def is_tenant_role(role: str) -> bool:
    """True for an effective tenant role (``tenant:…``) on a principal."""
    return role.startswith(TENANT_ROLE_PREFIX)


TenantExists = Callable[[str], Awaitable[bool]]
"""``async (tenant_id) -> bool``: whether a tenant with that id exists."""


async def tenant_exists(app: Any, tenant_id: str) -> bool | None:
    """Whether ``tenant_id`` names a known tenant, or ``None`` when nobody can say.

    A module that owns tenants (``tenants``) publishes ``app.state.tenant_exists``
    (a :data:`TenantExists`). Platform screens that take a tenant id from the
    URL ask through this, so they can refuse a typo without importing that
    module; with none installed the answer is ``None`` and they accept the id.
    """
    check: TenantExists | None = get_tenant_exists(app)
    if check is None:
        return None
    return bool(await check(tenant_id))


TenantMembers = Callable[[Any, str, Collection[str]], Awaitable[Collection[str]]]
"""``async (db, tenant_id, user_ids) -> the subset of user_ids that are members``.

``db`` is the caller's ``AsyncSession`` (typed ``Any``: core is SQLAlchemy-free),
so the lookup joins the request's unit of work instead of opening a second one."""


async def tenant_member_ids(
    app: Any, db: Any, tenant_id: str, user_ids: Collection[str]
) -> set[str] | None:
    """Which of *user_ids* belong to *tenant_id*, or ``None`` when nobody can say.

    The module that owns memberships (``tenants``) publishes
    ``app.state.tenant_members`` (a :data:`TenantMembers`). Code that must not
    reveal or act on accounts outside the active tenant (``sharing`` resolving
    a grantee) asks through this without importing that module. ``None`` means
    no membership store is installed; callers on a multi-tenant app treat it
    as "nobody" (fail closed).
    """
    check: TenantMembers | None = get_tenant_members(app)
    if check is None:
        return None
    if not user_ids:
        return set()
    return set(await check(db, tenant_id, user_ids))


__all__ = [
    "TENANT_ROLE_PREFIX",
    "TenancyMode",
    "TenantExists",
    "TenantMembers",
    "TenantRole",
    "is_tenant_role",
    "tenant_exists",
    "tenant_member_ids",
    "tenant_role",
]
