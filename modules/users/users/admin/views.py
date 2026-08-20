"""Inertia view routes for admin user management."""

from __future__ import annotations

import math
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from inertia import InertiaResponse
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission
from starlette.responses import RedirectResponse

from users.admin.service import UserService
from users.constants import PERM_USERS_MANAGE, sanitize_list_filters
from users.deps import get_user_service
from users.exceptions import UserNotFoundError
from users.roles_cache import get_roles_cache

router = APIRouter()

_PAGE_ADMIN_INDEX = "Users/Users/Index"
_PAGE_ADMIN_ADD = "Users/Users/AddPeople"
_PAGE_ADMIN_EDIT = "Users/Users/Edit"


async def _roles_payload(app) -> list[dict[str, str]]:
    """Shape roles-cache entries for Inertia props."""
    return [{"id": r.id, "name": r.name} for r in await get_roles_cache(app)]


@router.get(
    "/admin",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_USERS_MANAGE))],
)
async def admin_index(
    request: Request,
    inertia: InertiaDep,
    service: UserService = Depends(get_user_service),
    page: int = 1,
    per_page: int = 20,
    q: str | None = None,
    status: str | None = None,
    role: str | None = None,
    verified: str | None = None,
    sort: str = "email",
    order: str = "asc",
) -> InertiaResponse:
    clean_status, clean_verified, clean_sort, clean_order = sanitize_list_filters(
        status, verified, sort, order
    )
    # Clamp before building filters, with the same bounds the service applies
    # internally — the pagination prop must echo the values the query actually
    # ran with, or ?page=0 renders page-1 rows labelled "Page 0".
    page = max(page, 1)
    per_page = max(1, min(per_page, 200))
    filters = {
        "per_page": per_page,
        "search": q,
        "status": clean_status,
        "role_name": role or None,
        "verified": clean_verified,
        "sort": clean_sort,
        "order": clean_order,
    }
    users, total = await service.list_users(page=page, **filters)
    # A page requested past the end (a stale ?page= link, or the last row on
    # that page just got deleted) must be clamped and re-queried — otherwise
    # the client gets an empty `users` list with a nonzero `total`, which
    # renders a blank table instead of the last real page.
    # per_page is already clamped to >= 1 above, so this can't divide by zero.
    total_pages = max(1, math.ceil(total / per_page))
    if page > total_pages:
        page = total_pages
        users, total = await service.list_users(page=page, **filters)
    roles = await service.list_roles()
    aggregates = await service.count_user_states()
    return await inertia.render(
        _PAGE_ADMIN_INDEX,
        {
            "users": [u.model_dump(mode="json") for u in users],
            "pagination": {"page": page, "per_page": per_page, "total": total},
            "aggregates": aggregates,
            "query": q or "",
            "roles": [r.model_dump(mode="json") for r in roles],
            "filters": {
                "status": clean_status or "all",
                "role": role or "",
                "verified": clean_verified or "all",
                "sort": clean_sort,
                "order": clean_order,
            },
        },
    )


@router.get(
    "/admin/add",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_USERS_MANAGE))],
)
async def admin_add_people_page(
    request: Request,
    inertia: InertiaDep,
) -> InertiaResponse:
    """One screen for both ways of adding people, chosen by a mode switch.

    Create and invite were separate pages reached from separate buttons, which
    made an admin decide between them before seeing what either involved. They
    take almost the same inputs and differ in one respect — who sets the
    password — so the choice belongs inside the form.
    """
    mailer = getattr(getattr(request.app.state, "users", None), "mailer", None)
    return await inertia.render(
        _PAGE_ADMIN_ADD,
        {
            "roles": await _roles_payload(request.app),
            # Drives the copy-link panel: when nothing can be delivered, the
            # invite mode has to hand the link back instead. No mailer at all
            # delivers nothing — promising delivery there would be the one
            # answer that is certainly wrong.
            "mailer_delivers": bool(mailer is not None and getattr(mailer, "delivers_email", True)),
        },
    )


@router.get(
    "/admin/invite",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_USERS_MANAGE))],
)
async def admin_invite_redirect() -> RedirectResponse:
    """Old invite URL — the flow merged into /users/admin/add."""
    return RedirectResponse("/users/admin/add?mode=invite", status_code=307)


@router.get(
    "/admin/create",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_USERS_MANAGE))],
)
async def admin_create_redirect() -> RedirectResponse:
    """Old create URL — the flow merged into /users/admin/add."""
    return RedirectResponse("/users/admin/add?mode=create", status_code=307)


@router.get(
    "/admin/{user_id}",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_USERS_MANAGE))],
)
async def admin_edit_page(
    user_id: str,
    request: Request,
    inertia: InertiaDep,
    service: UserService = Depends(get_user_service),
) -> InertiaResponse:
    try:
        uid = uuid.UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404) from exc
    try:
        user_item = await service.get_list_item(uid)
    except UserNotFoundError:
        raise HTTPException(status_code=404) from None
    has_permissions = any(m.meta.name == "Permissions" for m in request.app.state.sm.modules)
    return await inertia.render(
        _PAGE_ADMIN_EDIT,
        {
            "user": user_item.model_dump(mode="json"),
            "roles": await _roles_payload(request.app),
            "has_permissions_module": has_permissions,
        },
    )
