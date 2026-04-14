"""Permission enforcement dependency for FastAPI endpoints."""

from __future__ import annotations

from fastapi import HTTPException, Request

WILDCARD = "*"

# "*" grants all permissions (superuser).
DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "admin": [WILDCARD],
    "user": [
        "products.view",
        "dashboard.view",
    ],
}


def resolve_permissions(
    roles: list[str],
    role_map: dict[str, list[str]] = DEFAULT_ROLE_PERMISSIONS,
) -> set[str]:
    """Resolve a set of roles into a flat set of permission strings."""
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
        permissions: set[str] = getattr(request.state, "resolved_permissions", None)  # type: ignore[assignment]
        if permissions is None:
            permissions = resolve_permissions(user.roles)
            request.state.resolved_permissions = permissions

        if WILDCARD in permissions:
            return

        if self.permission not in permissions:
            raise HTTPException(
                status_code=403,
                detail=f"Permission required: {self.permission}",
            )
