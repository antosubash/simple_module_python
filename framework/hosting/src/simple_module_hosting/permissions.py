"""Permission enforcement dependency for FastAPI endpoints."""

from __future__ import annotations

from fastapi import HTTPException, Request

# Maps Keycloak roles to application permissions.
# "*" is a wildcard granting all permissions (superuser).
# Modules register which permissions exist via PermissionRegistry,
# but this map controls which roles actually have them.
DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "admin": ["*"],
    "user": [
        "products.view",
        "dashboard.view",
    ],
}


def _resolve_permissions(
    roles: list[str],
    role_map: dict[str, list[str]] = DEFAULT_ROLE_PERMISSIONS,
) -> set[str]:
    """Resolve a set of roles into a flat set of permission strings."""
    permissions: set[str] = set()
    for role in roles:
        permissions.update(role_map.get(role, []))
    return permissions


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

        permissions = _resolve_permissions(user.roles)

        if "*" in permissions:
            return

        if self.permission not in permissions:
            raise HTTPException(
                status_code=403,
                detail=f"Permission required: {self.permission}",
            )
