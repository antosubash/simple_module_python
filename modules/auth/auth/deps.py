"""FastAPI auth dependencies — get_current_user, require_permission."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from simple_module_hosting.i18n_deps import TranslatorDep

from auth.contracts.schemas import UserContext

_ADMIN_ROLE = "admin"


async def get_current_user(request: Request, t: TranslatorDep) -> UserContext:
    """Extract the authenticated user from request state.

    The auth middleware must set ``request.state.user`` before this runs.
    """
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail=t.t("auth.errors.not_authenticated"))
    return user


CurrentUser = Annotated[UserContext, Depends(get_current_user)]


def require_permission(*permissions: str):
    """Create a dependency that checks if the user has required permissions.

    Usage::

        @router.post("/", dependencies=[Depends(require_permission("products.create"))])
        async def create_product(...): ...
    """

    async def check(
        request: Request,
        t: TranslatorDep,
        user: UserContext = Depends(get_current_user),
    ):
        # Admin role bypasses permission checks
        if _ADMIN_ROLE in user.roles:
            return

        # Get permission registry from app state
        perm_registry = request.app.state.sm.permissions
        user_perms = perm_registry.get_permissions_for_roles(user.roles)

        if not any(p in user_perms for p in permissions):
            raise HTTPException(
                status_code=403,
                detail=t.t(
                    "auth.errors.missing_permission",
                    permissions=", ".join(permissions),
                ),
            )

    return Depends(check)
