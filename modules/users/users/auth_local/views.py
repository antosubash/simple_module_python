"""Inertia view routes for local-credential auth (login/register/reset/verify/profile)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from inertia import InertiaResponse
from simple_module_core.redirect_safety import SESSION_NEXT_KEY, safe_next_or_none
from simple_module_db.deps import get_db
from simple_module_hosting.inertia_deps import InertiaDep
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from users.auth_local.invite_preview import preview_invite
from users.auth_local.token_preview import decode_verify_token, preview_reset
from users.bootstrap import resolve_bootstrap_credentials
from users.contracts.schemas import UserRead
from users.manager import UserManager, get_user_manager
from users.models import User

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

_SECONDS_PER_MINUTE = 60
_SECONDS_PER_HOUR = 60 * 60
_SECONDS_PER_DAY = 60 * 60 * 24


def _mailer_delivers(request: Request) -> bool:
    """Whether the configured mailer actually sends anything.

    Drives the amber "the link is in the server log" callout: the console
    mailer writes the link to stdout, so telling someone to check their inbox
    would be the one answer that is certainly wrong.
    """
    mailer = getattr(getattr(request.app.state, "users", None), "mailer", None)
    return bool(mailer is not None and getattr(mailer, "delivers_email", True))


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
                # Never "" — UsersSettings normalises a blanked value back to
                # the default, so every consumer (here, Keycloak, OAuth) gets
                # a usable target rather than each guarding for itself.
                or users_settings.login_redirect_url
            ),
            "oauth_providers": users_state.oauth_providers,
            # "Keep me signed in for N days" reads this rather than spelling
            # the number in the copy, so shortening the window in settings
            # cannot leave the checkbox lying about what it does.
            "remember_me_days": users_settings.remember_me_max_age_seconds // _SECONDS_PER_DAY,
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
async def forgot_password_page(request: Request, inertia: InertiaDep) -> InertiaResponse:
    users_settings = request.app.state.users.settings
    return await inertia.render(
        _PAGE_FORGOT_PASSWORD,
        {
            "reset_link_lifetime_minutes": (
                users_settings.reset_password_token_lifetime_seconds // _SECONDS_PER_MINUTE
            ),
            "mailer_delivers": _mailer_delivers(request),
        },
    )


@router.get("/reset-password", response_model=None)
async def reset_password_page(
    request: Request,
    inertia: InertiaDep,
    user_manager: UserManager = Depends(get_user_manager),
    token: str = "",
) -> InertiaResponse:
    """Decide the dead-link state here rather than after a failed submit.

    Typing a new password twice only to be told the link ran out an hour ago
    is the worst moment to find out. The token says so on arrival, so the page
    is handed the answer.
    """
    users_settings = request.app.state.users.settings
    preview = await preview_reset(token, user_manager)
    return await inertia.render(
        _PAGE_RESET_PASSWORD,
        {
            "token": token,
            # The address the reset is for — "Save and sign in" needs it to
            # complete the sign-in without asking for it again.
            "email": preview["email"] if preview else None,
            # A missing token is its own state ("use the link from your
            # email"); this is specifically a link that was real and is not
            # any more.
            "expired": bool(token) and preview is None,
            "reset_link_lifetime_minutes": (
                users_settings.reset_password_token_lifetime_seconds // _SECONDS_PER_MINUTE
            ),
        },
    )


@router.get("/verify", response_model=None)
async def verify_page(request: Request, inertia: InertiaDep, token: str = "") -> InertiaResponse:
    users_settings = request.app.state.users.settings
    # Deliberately ignores expiry: an expired verification link is exactly
    # when the address is worth recovering, so "Resend verification" can offer
    # to send another one there instead of asking for it to be retyped.
    claims = decode_verify_token(token, users_settings.verification_token_secret)
    return await inertia.render(
        _PAGE_VERIFY_EMAIL,
        {
            "token": token,
            "email": claims.get("email") if claims else None,
            "verification_lifetime_hours": (
                users_settings.verification_token_lifetime_seconds // _SECONDS_PER_HOUR
            ),
        },
    )


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
async def profile_page(
    request: Request,
    inertia: InertiaDep,
    db: AsyncSession = Depends(get_db),
) -> InertiaResponse:
    """The signed-in user's own record, loaded rather than inferred.

    The page used to read ``auth.user.full_name`` and ``auth.user.is_verified``
    off the shared props, where neither has ever existed — ``UserContext``
    carries id, email, name and roles. The name field therefore always loaded
    blank and the badge always read "unverified". Loading the row is the fix:
    it is also the only source for ``is_external`` (which hides the password
    card) and ``last_login_at`` (which dates this browser's session).
    """
    ctx = getattr(request.state, "user", None)
    if ctx is None:
        raise HTTPException(status_code=401)
    user = await db.get(User, uuid.UUID(ctx.id))
    if user is None:
        raise HTTPException(status_code=401)
    return await inertia.render(
        _PAGE_PROFILE,
        {"user": UserRead.model_validate(user).model_dump(mode="json")},
    )
