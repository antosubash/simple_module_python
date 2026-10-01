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

from enum import StrEnum

TENANT_ROLE_PREFIX = "tenant:"


class TenantRole(StrEnum):
    """A member's role within one tenant."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


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


__all__ = ["TENANT_ROLE_PREFIX", "TenantRole", "is_tenant_role", "tenant_role"]
