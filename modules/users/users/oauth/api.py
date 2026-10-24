"""OAuth/OIDC login routes — a single provider-agnostic dispatcher.

One pair of routes (``/auth/{provider}/login`` + ``/auth/{provider}/callback``)
serves every provider. The client is resolved per request from
``app.state.users.oauth_clients`` — the cache built in ``UsersModule.on_startup``
from hydrated DB settings and rebuilt on ``SettingsReloaded``. Routes mount
unconditionally at construction (before settings hydrate), so providers
configured through the settings UI work and take effect without a restart.

Why a custom handler rather than ``fastapi_users.get_oauth_router``: the stock
``/callback`` returns 204; Inertia needs the browser to land on a real page, so
``/callback`` returns a 303 redirect to the stashed deep link (or
``login_redirect_url``) with the auth
cookie attached. Find-or-create + email-association go through
``UserManager.oauth_callback``. State CSRF uses Starlette's signed session
cookie.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi_users import exceptions as fu_exceptions
from simple_module_core.redirect_safety import SESSION_NEXT_KEY, safe_next_or_none
from starlette.responses import RedirectResponse

from users.constants import OAUTH_REGISTRATION_REQUEST_FLAG
from users.deps import auth_backend, get_user_manager

if TYPE_CHECKING:
    from users.manager import UserManager
    from users.models import User
    from users.oauth.providers import OAuthProvider

_SESSION_STATE_KEY_FMT = "oauth_state:{provider}"
_CALLBACK_ROUTE_NAME = "users_oauth_callback"


def _resolve_provider(request: Request, provider: str) -> OAuthProvider:
    """Return the configured provider by name, or raise 404."""
    found = request.app.state.users.oauth_clients.get(provider)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="OAUTH_PROVIDER_NOT_FOUND"
        )
    return found


async def _existing_account(
    user_manager: UserManager, provider: str, account_id: str, account_email: str
) -> tuple[User | None, bool]:
    """Find an existing identity or email, and whether it is already linked.

    Mirrors the callback's two lookups: the linked OAuth account first, then
    an account by email (which requires provider verification before linking).
    ``(None, False)`` means the callback would create a new account.
    """
    try:
        return await user_manager.get_by_oauth_account(provider, account_id), True
    except fu_exceptions.UserNotExists:
        pass
    try:
        return await user_manager.get_by_email(account_email), False
    except fu_exceptions.UserNotExists:
        return None, False


def _unproven_account(user: User) -> bool:
    """An account nobody has proven owns its email.

    Linking an SSO identity to it by email would hand the provider's user an
    account someone else may already control: register the victim's address
    with a password (GH #547), or sign in first through a provider that gives
    no email proof so an unverified SSO account holds the attacker's link
    (#622), then wait for the real owner to sign in with a verified email. A
    pending invite links: its password is random and an admin chose the
    address, so nobody could have pre-created it.
    """
    return not user.is_verified and user.invited_at is None


def register_oauth_routes(api_router: APIRouter) -> None:
    """Mount the provider-agnostic OAuth dispatcher under ``/auth``."""
    router = APIRouter(prefix="/auth", tags=["users-auth"])

    @router.get("/{provider}/login")
    async def begin(request: Request, provider: str) -> RedirectResponse:
        """Generate a state nonce, stash it in the session, redirect to the IdP."""
        provider_obj = _resolve_provider(request, provider)
        state = secrets.token_urlsafe(32)
        request.session[_SESSION_STATE_KEY_FMT.format(provider=provider)] = state
        callback_url = str(request.url_for(_CALLBACK_ROUTE_NAME, provider=provider))
        authorization_url = await provider_obj.client.get_authorization_url(callback_url, state)
        return RedirectResponse(authorization_url, status_code=302)

    @router.get("/{provider}/callback", name=_CALLBACK_ROUTE_NAME)
    async def callback(
        request: Request,
        provider: str,
        code: str | None = None,
        state: str | None = None,
        user_manager: UserManager = Depends(get_user_manager),
        strategy=Depends(auth_backend.get_strategy),
    ) -> RedirectResponse:
        """Verify state, exchange code, find-or-create user, set cookie, redirect."""
        provider_obj = _resolve_provider(request, provider)
        state_key = _SESSION_STATE_KEY_FMT.format(provider=provider)
        expected_state = request.session.pop(state_key, None)
        if not state or not expected_state or not secrets.compare_digest(state, expected_state):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="OAUTH_INVALID_STATE"
            )
        if not code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="OAUTH_MISSING_CODE"
            )

        callback_url = str(request.url_for(_CALLBACK_ROUTE_NAME, provider=provider))
        token = await provider_obj.client.get_access_token(code, callback_url)
        account_id, account_email, email_verified = await provider_obj.get_identity(
            token["access_token"]
        )
        if account_email is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAUTH_NO_EMAIL")

        existing, linked = await _existing_account(
            user_manager, provider, account_id, account_email
        )
        # An OAuth sign-in is a signup when nobody holds this identity yet, and
        # with ``allow_signup`` off it must not be one: an operator enabling
        # SSO for staff would otherwise open signup to the provider's whole
        # user base (GH #543). Existing accounts still link and sign in.
        if existing is None and not request.app.state.users.settings.allow_signup:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="OAUTH_SIGNUP_DISABLED"
            )
        if existing is not None and not linked and _unproven_account(existing):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="OAUTH_ACCOUNT_NOT_VERIFIED"
            )

        # Mark this request so the manager's on_after_register provisions a
        # *new* OAuth user as external (null password). Ignored when the login
        # links to an existing account (on_after_register won't fire).
        setattr(request.state, OAUTH_REGISTRATION_REQUEST_FLAG, True)
        try:
            user = await user_manager.oauth_callback(
                provider,
                token["access_token"],
                account_id,
                account_email,
                token.get("expires_at"),
                token.get("refresh_token"),
                request,
                associate_by_email=email_verified,
                is_verified_by_default=email_verified,
            )
        except fu_exceptions.UserAlreadyExists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OAUTH_USER_ALREADY_EXISTS",
            ) from None

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="LOGIN_BAD_CREDENTIALS"
            )

        login_response = await auth_backend.login(strategy, user)
        await user_manager.on_after_login(user, request, login_response)

        # Honour the deep link AuthMiddleware stashed before bouncing this
        # visitor to login, exactly as the password and Keycloak paths do.
        # Popped, not read: leaving it would send some later, unrelated visit
        # to /users/login off to a stale destination. Re-sanitised on the way
        # out because the value lands in a Location header.
        redirect_url = (
            safe_next_or_none(request.session.pop(SESSION_NEXT_KEY, None))
            or request.app.state.users.settings.login_redirect_url
        )
        redirect = RedirectResponse(redirect_url, status_code=303)
        for key, value in login_response.headers.items():
            if key.lower() == "set-cookie":
                redirect.raw_headers.append((b"set-cookie", value.encode("latin-1")))
        return redirect

    api_router.include_router(router)
