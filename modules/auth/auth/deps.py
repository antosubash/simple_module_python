"""FastAPI auth dependencies — get_current_user, require_permission."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from simple_module_core.deprecation import deprecated
from simple_module_core.permissions import ADMIN_ROLE, grants
from simple_module_hosting.i18n_deps import TranslatorDep
from simple_module_hosting.permissions import ensure_resolved_permissions
from simple_module_hosting.token_guard import GATE_PERMISSION, mark_token_gate

from auth.contracts.schemas import UserContext


async def get_current_user(request: Request, t: TranslatorDep) -> UserContext:
    """Extract the authenticated user from request state.

    The auth middleware must set ``request.state.user`` before this runs.
    """
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail=t.t("auth.errors.not_authenticated"))
    return user


CurrentUser = Annotated[UserContext, Depends(get_current_user)]


@deprecated(remove_in="0.1.0", use="simple_module_hosting.permissions.RequiresPermission")
def require_permission(*permissions: str):
    """Legacy any-of gate, removed in 0.1.0; use ``RequiresPermission`` instead.

    Retains the role-based admin bypass and cached permission behaviour for
    compatibility. ``RequiresPermission`` rechecks a principal demoted during
    the request; this helper does not.
    """

    async def check(
        request: Request,
        t: TranslatorDep,
        user: UserContext = Depends(get_current_user),
    ):
        # Admin role bypasses permission checks — but not for a token: an
        # admin's PAT is worth only the scopes it carries, and the resolved
        # set below already applies that cap.
        if ADMIN_ROLE in user.roles and user.scopes is None:
            return

        # The same resolution RequiresPermission reads: the registry's role map
        # plus module grant sources. This used to call get_permissions_for_roles
        # without a map, which grants every non-admin role nothing (GH #337).
        held = await ensure_resolved_permissions(request)
        if not any(grants(held, p) for p in permissions):
            raise HTTPException(
                status_code=403,
                detail=t.t(
                    "auth.errors.missing_permission",
                    permissions=", ".join(permissions),
                ),
            )

    # A permission gate: API tokens may reach the route, capped at their
    # scopes (``simple_module_hosting.token_guard``).
    return Depends(mark_token_gate(check, GATE_PERMISSION))
