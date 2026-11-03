"""Tenant-claim and tenant-role policy shared by the OIDC providers."""

from __future__ import annotations

import logging
from typing import Any

from simple_module_core.tenancy import is_tenant_role
from simple_module_db import is_valid_tenant_id

logger = logging.getLogger(__name__)


def trusted_tenant(value: Any, *, trust_claim: bool) -> str | None:
    """The ``tenant_id`` claim, if the operator trusts it and it is well-formed.

    The claim is the IdP's word, not ours: it is ignored unless the operator
    vouches for the realm mapper (``trust_tenant_claim``), and even then a
    registered tenant resolver overrides it every request. It must also pass
    the same id check as any other tenant id taken from outside.
    """
    if value is None or not trust_claim:
        return None
    if not is_valid_tenant_id(value):
        logger.warning("Ignoring malformed tenant_id claim %r", value)
        return None
    return value


def without_tenant_roles(roles: list[str], *, warned: set[str], provider: str) -> list[str]:
    """Drop ``tenant:*`` roles: only the tenants module may grant them, for
    the active tenant. A ``role_mapping`` entry producing one would
    otherwise hand every user that tenant role in every tenant."""
    kept = []
    for role in roles:
        if not is_tenant_role(role):
            kept.append(role)
        elif role not in warned:
            warned.add(role)
            logger.warning(
                "%s role_mapping produced tenant role %r; ignored "
                "(tenant roles come from memberships only)",
                provider,
                role,
            )
    return kept
