"""Permission enforcement dependency for FastAPI endpoints."""

from __future__ import annotations

from fastapi import HTTPException, Request
from simple_module_core.permissions import DEFAULT_ROLE_PERMISSIONS, WILDCARD

__all__ = [
    "DEFAULT_ROLE_PERMISSIONS",
    "PERMISSION_DENIED_PREFIX",
    "WILDCARD",
    "RequiresPermission",
    "expand_permissions",
    "resolve_permissions",
]

# How a denial spells the missing permission in ``HTTPException.detail``.
# Exported because the error-page handler parses the name back out of it to
# tell the visitor what to ask an admin for; two copies of this literal in two
# files is exactly the drift that would leave the 403 page with no permission
# to name and no test to notice.
PERMISSION_DENIED_PREFIX = "Permission required: "


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


def expand_permissions(
    resolved: set[str],
    all_permissions: list[str],
) -> list[str]:
    """Expand wildcard to the full permission list for frontend consumption."""
    if WILDCARD in resolved:
        return sorted(set(all_permissions))
    return sorted(resolved)


class RequiresPermission:
    """FastAPI dependency that enforces a specific permission.

    Usage::

        @router.post("/", dependencies=[Depends(RequiresPermission("products.create"))])
        async def create_product(...):
            ...
    """

    def __init__(self, permission: str) -> None:
        self.permission = permission

    def __call__(self, request: Request) -> None:
        user = getattr(request.state, "user", None)
        if user is None:
            raise HTTPException(status_code=401, detail="Authentication required")

        # Use cached permissions from middleware if available
        permissions: set[str] | None = getattr(request.state, "resolved_permissions", None)
        if permissions is None:
            # Fallback: middleware did not run — consult registry role_map if available
            sm = getattr(getattr(request.app, "state", None), "sm", None)
            perm_registry = getattr(sm, "permissions", None) if sm is not None else None
            role_map = perm_registry.role_map if perm_registry is not None else None
            permissions = resolve_permissions(user.roles, role_map=role_map)
            request.state.resolved_permissions = permissions

        if WILDCARD in permissions:
            return

        if self.permission not in permissions:
            raise HTTPException(
                status_code=403,
                detail=f"{PERMISSION_DENIED_PREFIX}{self.permission}",
            )
