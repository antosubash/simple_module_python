"""Inertia view routes for the users module."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from inertia import InertiaResponse
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission
from starlette.responses import RedirectResponse

from users.constants import PERM_USERS_MANAGE
from users.deps import get_user_service
from users.endpoints.api_admin import (
    _ALLOWED_ORDER,
    _ALLOWED_SORT,
    _ALLOWED_STATUS,
    _ALLOWED_VERIFIED,
)
from users.exceptions import UserNotFoundError
from users.roles_cache import get_roles_cache
from users.service import UserService

router = APIRouter()

# Inertia page identifiers
_PAGE_LOGIN = "Users/Login"
_PAGE_REGISTER = "Users/Register"
_PAGE_FORGOT_PASSWORD = "Users/ForgotPassword"
_PAGE_RESET_PASSWORD = "Users/ResetPassword"
_PAGE_VERIFY_EMAIL = "Users/VerifyEmail"
_PAGE_ACCEPT_INVITE = "Users/AcceptInvite"
_PAGE_PROFILE = "Users/Profile"
_PAGE_ADMIN_INDEX = "Users/Users/Index"
_PAGE_ADMIN_INVITE = "Users/Users/Invite"
_PAGE_ADMIN_EDIT = "Users/Users/Edit"


async def _roles_payload(app) -> list[dict[str, str]]:
    """Shape roles-cache entries for Inertia props."""
    return [{"id": r.id, "name": r.name} for r in await get_roles_cache(app)]


# ── Public auth pages ───────────────────────────────────────────


@router.get("/login", response_model=None)
async def login_page(request: Request, inertia: InertiaDep) -> InertiaResponse:
    users_settings = request.app.state.users.settings
    # In development only, surface the bootstrap credentials as click-to-fill
    # buttons so manual QA doesn't need to retype them. Never exposed in
    # production, regardless of whether the vars are set.
    dev_accounts: list[dict[str, str]] = []
    if request.app.state.sm.settings.is_development:
        if users_settings.bootstrap_email and users_settings.bootstrap_password:
            dev_accounts.append(
                {
                    "label": "Admin",
                    "email": users_settings.bootstrap_email,
                    "password": users_settings.bootstrap_password,
                }
            )
        if users_settings.bootstrap_user_email and users_settings.bootstrap_user_password:
            dev_accounts.append(
                {
                    "label": "User",
                    "email": users_settings.bootstrap_user_email,
                    "password": users_settings.bootstrap_user_password,
                }
            )
    return await inertia.render(
        _PAGE_LOGIN,
        {"allow_signup": users_settings.allow_signup, "dev_accounts": dev_accounts},
    )


@router.post("/logout", response_model=None)
async def logout(request: Request) -> RedirectResponse:
    """Clear the session + auth cookie. POST-only to resist cross-site `<img>`
    logout attacks — the menu's logout link submits this as an Inertia form."""
    request.session.clear()
    cookie_name = request.app.state.users.settings.cookie_name
    # 303 forces the follow-up to GET — Inertia treats the redirect as a full
    # navigation rather than replaying the POST.
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(cookie_name, path="/")
    return response


@router.get("/register", response_model=None)
async def register_page(request: Request, inertia: InertiaDep) -> InertiaResponse:
    if not request.app.state.users.settings.allow_signup:
        raise HTTPException(status_code=404)
    return await inertia.render(_PAGE_REGISTER, {})


@router.get("/forgot-password", response_model=None)
async def forgot_password_page(inertia: InertiaDep) -> InertiaResponse:
    return await inertia.render(_PAGE_FORGOT_PASSWORD, {})


@router.get("/reset-password", response_model=None)
async def reset_password_page(inertia: InertiaDep, token: str = "") -> InertiaResponse:
    return await inertia.render(_PAGE_RESET_PASSWORD, {"token": token})


@router.get("/verify", response_model=None)
async def verify_page(inertia: InertiaDep, token: str = "") -> InertiaResponse:
    return await inertia.render(_PAGE_VERIFY_EMAIL, {"token": token})


@router.get("/invite/accept", response_model=None)
async def accept_invite_page(inertia: InertiaDep, token: str = "") -> InertiaResponse:
    return await inertia.render(_PAGE_ACCEPT_INVITE, {"token": token})


# ── Authenticated pages ─────────────────────────────────────────


@router.get("/me", response_model=None)
async def profile_page(inertia: InertiaDep) -> InertiaResponse:
    return await inertia.render(_PAGE_PROFILE, {})


# ── Admin pages ─────────────────────────────────────────────────


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
    clean_status = status if status in _ALLOWED_STATUS else None
    clean_verified = verified if verified in _ALLOWED_VERIFIED else None
    clean_sort = sort if sort in _ALLOWED_SORT else "email"
    clean_order = order if order in _ALLOWED_ORDER else "asc"
    users, total = await service.list_users(
        page=page,
        per_page=per_page,
        search=q,
        status=clean_status,
        role_name=role or None,
        verified=clean_verified,
        sort=clean_sort,
        order=clean_order,
    )
    return await inertia.render(
        _PAGE_ADMIN_INDEX,
        {
            "users": [u.model_dump(mode="json") for u in users],
            "pagination": {"page": page, "per_page": per_page, "total": total},
            "query": q or "",
            "roles": await _roles_payload(request.app),
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
    "/admin/invite",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_USERS_MANAGE))],
)
async def admin_invite_page(
    request: Request,
    inertia: InertiaDep,
) -> InertiaResponse:
    return await inertia.render(
        _PAGE_ADMIN_INVITE,
        {
            "roles": await _roles_payload(request.app),
        },
    )


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
    has_permissions = any(
        m.meta.name == "Permissions" for m in request.app.state.sm.modules
    )
    return await inertia.render(
        _PAGE_ADMIN_EDIT,
        {
            "user": user_item.model_dump(mode="json"),
            "roles": await _roles_payload(request.app),
            "has_permissions_module": has_permissions,
        },
    )
