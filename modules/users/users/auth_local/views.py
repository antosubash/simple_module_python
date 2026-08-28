"""Inertia view routes for local-credential auth (login/register/reset/verify/profile)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from inertia import InertiaResponse
from simple_module_core.redirect_safety import SESSION_NEXT_KEY, safe_next_or_none
from simple_module_hosting.inertia_deps import InertiaDep
from starlette.responses import RedirectResponse

from users.auth_local.invite_preview import preview_invite
from users.bootstrap import resolve_bootstrap_credentials
from users.manager import UserManager, get_user_manager

router = APIRouter()

# (label, email-key, password-key) for the dev-quick-login buttons, in the
# order they should appear on the page.
_DEV_ACCOUNT_SPECS: tuple[tuple[str, str, str], ...] = (
    ("Admin", "bootstrap_email", "bootstrap_password"),
    ("User", "bootstrap_user_email", "bootstrap_user_password"),
)

_PAGE_LOGIN = "Users/Login"
_PAGE_REGISTER = "Users/Register"
_PAGE_FORGOT_PASSWORD = "Users/ForgotPassword"
_PAGE_RESET_PASSWORD = "Users/ResetPassword"
_PAGE_VERIFY_EMAIL = "Users/VerifyEmail"
_PAGE_ACCEPT_INVITE = "Users/AcceptInvite"
_PAGE_PROFILE = "Users/Profile"


@router.get("/login", response_model=None)
async def login_page(request: Request, inertia: InertiaDep) -> InertiaResponse:
    users_state = request.app.state.users
    users_settings = users_state.settings
    # In development only, surface the bootstrap credentials as click-to-fill
    # buttons so manual QA doesn't need to retype them. Never exposed in
    # production, regardless of whether the vars are set. Uses the same
    # resolution as the boot-time seeder so the buttons appear iff a seed
    # admin would actually be created.
    dev_accounts: list[dict[str, str]] = []
    if request.app.state.sm.settings.is_development:
        resolved = resolve_bootstrap_credentials(users_settings)
        for label, email_key, password_key in _DEV_ACCOUNT_SPECS:
            if resolved[email_key] and resolved[password_key]:
                dev_accounts.append(
                    {
                        "label": label,
                        "email": resolved[email_key],
                        "password": resolved[password_key],
                    }
                )
    return await inertia.render(
        _PAGE_LOGIN,
        {
            "allow_signup": users_settings.allow_signup,
            "dev_accounts": dev_accounts,
            # Where AuthMiddleware bounced them from, when it bounced them.
            # Read, not popped: a reload of the login page must not silently
            # downgrade the deep link to the default landing page. The POST
            # handler clears it once login actually succeeds.
            "login_redirect_url": (
                safe_next_or_none(request.session.get(SESSION_NEXT_KEY))
                or users_settings.login_redirect_url
                # An admin can blank the DB-backed setting via the generic
                # module-settings editor (no non-empty validator on the
                # field) — never hand the frontend "" as a navigation
                # target (Inertia's router.visit("") just reloads the
                # current page, stranding the user on /login).
                or "/dashboard/"
            ),
            "oauth_providers": users_state.oauth_providers,
        },
    )


@router.post("/logout", response_model=None)
async def logout(request: Request) -> RedirectResponse:
    """POST-only to resist cross-site `<img>` logout attacks — the menu's
    logout link submits this as an Inertia form."""
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
async def accept_invite_page(
    inertia: InertiaDep,
    user_manager: UserManager = Depends(get_user_manager),
    token: str = "",
) -> InertiaResponse:
    """Show who the invite is for and what it grants, before asking for a password."""
    invite = await preview_invite(token, user_manager)
    return await inertia.render(
        _PAGE_ACCEPT_INVITE,
        {
            "token": token,
            "invite": invite,
        },
    )


@router.get("/me", response_model=None)
async def profile_page(inertia: InertiaDep) -> InertiaResponse:
    return await inertia.render(_PAGE_PROFILE, {})
