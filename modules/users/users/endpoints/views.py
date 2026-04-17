"""Inertia view routes for the users module."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from inertia import InertiaResponse
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission
from starlette.responses import RedirectResponse

from users.deps import get_user_service
from users.roles_cache import get_roles_cache
from users.service import UserService

router = APIRouter()


# ── Public auth pages ───────────────────────────────────────────


@router.get("/login", response_model=None)
async def login_page(request: Request, inertia: InertiaDep) -> InertiaResponse:
    users_settings = request.app.state.users_settings
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
        "Users/Login",
        {"allow_signup": users_settings.allow_signup, "dev_accounts": dev_accounts},
    )


@router.post("/logout", response_model=None)
async def logout(request: Request) -> RedirectResponse:
    """Clear the session + auth cookie. POST-only to resist cross-site `<img>`
    logout attacks — the menu's logout link submits this as an Inertia form."""
    request.session.clear()
    cookie_name = request.app.state.users_settings.cookie_name
    # 303 forces the follow-up to GET — Inertia treats the redirect as a full
    # navigation rather than replaying the POST.
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(cookie_name, path="/")
    return response


@router.get("/register", response_model=None)
async def register_page(request: Request, inertia: InertiaDep) -> InertiaResponse:
    if not request.app.state.users_settings.allow_signup:
        raise HTTPException(status_code=404)
    return await inertia.render("Users/Register", {})


@router.get("/forgot-password", response_model=None)
async def forgot_password_page(inertia: InertiaDep) -> InertiaResponse:
    return await inertia.render("Users/ForgotPassword", {})


@router.get("/reset-password", response_model=None)
async def reset_password_page(inertia: InertiaDep, token: str = "") -> InertiaResponse:
    return await inertia.render("Users/ResetPassword", {"token": token})


@router.get("/verify", response_model=None)
async def verify_page(inertia: InertiaDep, token: str = "") -> InertiaResponse:
    return await inertia.render("Users/VerifyEmail", {"token": token})


@router.get("/invite/accept", response_model=None)
async def accept_invite_page(inertia: InertiaDep, token: str = "") -> InertiaResponse:
    return await inertia.render("Users/AcceptInvite", {"token": token})


# ── Authenticated pages ─────────────────────────────────────────


@router.get("/me", response_model=None)
async def profile_page(inertia: InertiaDep) -> InertiaResponse:
    return await inertia.render("Users/Profile", {})


# ── Admin pages ─────────────────────────────────────────────────


@router.get(
    "/admin",
    response_model=None,
    dependencies=[Depends(RequiresPermission("users.manage"))],
)
async def admin_index(
    request: Request,
    inertia: InertiaDep,
    service: UserService = Depends(get_user_service),
    page: int = 1,
    per_page: int = 20,
    q: str | None = None,
) -> InertiaResponse:
    users, total = await service.list_users(page=page, per_page=per_page, search=q)
    return await inertia.render(
        "Users/Users/Index",
        {
            "users": [u.model_dump(mode="json") for u in users],
            "pagination": {"page": page, "per_page": per_page, "total": total},
            "query": q or "",
            "roles": [{"id": r.id, "name": r.name} for r in await get_roles_cache(request.app)],
        },
    )


@router.get(
    "/admin/invite",
    response_model=None,
    dependencies=[Depends(RequiresPermission("users.manage"))],
)
async def admin_invite_page(
    request: Request,
    inertia: InertiaDep,
) -> InertiaResponse:
    return await inertia.render(
        "Users/Users/Invite",
        {
            "roles": [{"id": r.id, "name": r.name} for r in await get_roles_cache(request.app)],
        },
    )


@router.get(
    "/admin/{user_id}",
    response_model=None,
    dependencies=[Depends(RequiresPermission("users.manage"))],
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
    user_item = await service.get_list_item(uid)
    if user_item is None:
        raise HTTPException(status_code=404)
    return await inertia.render(
        "Users/Users/Edit",
        {
            "user": user_item.model_dump(mode="json"),
            "roles": [{"id": r.id, "name": r.name} for r in await get_roles_cache(request.app)],
        },
    )
