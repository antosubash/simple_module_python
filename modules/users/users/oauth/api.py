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

import logging
import secrets
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi_users import exceptions as fu_exceptions
from httpx import HTTPError
from httpx_oauth.exceptions import HTTPXOAuthError
from simple_module_core.redirect_safety import SESSION_NEXT_KEY, safe_next_or_none
from starlette.responses import RedirectResponse

from users.core.constants import OAUTH_REGISTRATION_REQUEST_FLAG
from users.oauth.errors import refuse_login
from users.web.deps import auth_backend, get_user_manager

if TYPE_CHECKING:
    from users.accounts.manager import UserManager
    from users.core.settings import UsersSettings
    from users.models import User
    from users.oauth.providers import LoginSecrets, OAuthProvider

logger = logging.getLogger(__name__)

_SESSION_STATE_KEY_FMT = "oauth_state:{provider}"
_SESSION_LOGIN_KEY_FMT = "oauth_login:{provider}"
_CALLBACK_ROUTE_NAME = "users_oauth_callback"


def _login_secrets(value: object) -> LoginSecrets | None:
    """The stored PKCE verifier and nonce, or ``None`` if absent or malformed."""
    if not isinstance(value, dict):
        return None
    verifier, nonce = value.get("verifier"), value.get("nonce")
    if not isinstance(verifier, str) or not verifier or not isinstance(nonce, str) or not nonce:
        return None
    return {"verifier": verifier, "nonce": nonce}


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


def _may_create_account(settings: UsersSettings, provider: str, email_verified: bool) -> bool:
    """Whether a first sign-in through ``provider`` may create an account.

    A provider listed in ``oauth_signup_providers`` provisions with signup
    closed, but only when it proved the email; the listing applies with signup
    open too, so it never widens what the provider can do (#874). Any other
    provider follows ``allow_signup``.
    """
    if provider in settings.oauth_signup_providers:
        return email_verified
    return settings.allow_signup


def register_oauth_routes(api_router: APIRouter) -> None:
    """Mount the provider-agnostic OAuth dispatcher under ``/auth``."""
    router = APIRouter(prefix="/auth", tags=["users-auth"])

    @router.get("/{provider}/login")
    async def begin(request: Request, provider: str) -> RedirectResponse:
        """Generate a state nonce, stash it in the session, redirect to the IdP."""
        provider_obj = _resolve_provider(request, provider)
        state = secrets.token_urlsafe(32)
        request.session[_SESSION_STATE_KEY_FMT.format(provider=provider)] = state
        login: LoginSecrets | None = None
        if provider_obj.uses_pkce:
            login = {"verifier": secrets.token_urlsafe(64), "nonce": secrets.token_urlsafe(32)}
            request.session[_SESSION_LOGIN_KEY_FMT.format(provider=provider)] = login
        callback_url = str(request.url_for(_CALLBACK_ROUTE_NAME, provider=provider))
        authorization_url = await provider_obj.authorization_url(callback_url, state, login)
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
        expected_state = request.session.get(state_key)
        # Compared before anything is spent, so a forged or stray reply cannot
        # consume the pending login; the matching reply spends the state together
        # with that login's PKCE verifier and nonce.
        if (
            not state
            or not isinstance(expected_state, str)
            or not secrets.compare_digest(state, expected_state)
        ):
            return refuse_login(request, "OAUTH_INVALID_STATE")
        request.session.pop(state_key, None)
        login = _login_secrets(
            request.session.pop(_SESSION_LOGIN_KEY_FMT.format(provider=provider), None)
        )
        if provider_obj.uses_pkce and login is None:
            return refuse_login(request, "OAUTH_INVALID_STATE")
        if "error" in request.query_params:
            return refuse_login(request, "OAUTH_PROVIDER_ERROR")
        if not code:
            return refuse_login(request, "OAUTH_MISSING_CODE")

        callback_url = str(request.url_for(_CALLBACK_ROUTE_NAME, provider=provider))
        try:
            token = await provider_obj.exchange_code(code, callback_url, login)
            account_id, account_email, email_verified = await provider_obj.get_identity(
                token, login
            )
        except (HTTPXOAuthError, HTTPError) as exc:
            # The browser only sees OAUTH_PROVIDER_ERROR; say why for the operator.
            logger.warning("OAuth sign-in through %s refused: %s", provider, exc)
            return refuse_login(request, "OAUTH_PROVIDER_ERROR")
        if account_email is None:
            return refuse_login(request, "OAUTH_NO_EMAIL")

        existing, linked = await _existing_account(
            user_manager, provider, account_id, account_email
        )
        # An OAuth sign-in is a signup when nobody holds this identity yet, and
        # with ``allow_signup`` off it must not be one: an operator enabling
        # SSO for staff would otherwise open signup to the provider's whole
        # user base (GH #543). Existing accounts still link and sign in.
        settings = request.app.state.users.settings
        if existing is None and not _may_create_account(settings, provider, email_verified):
            return refuse_login(request, "OAUTH_SIGNUP_DISABLED", status.HTTP_403_FORBIDDEN)
        if existing is not None and not linked and _unproven_account(existing):
            return refuse_login(request, "OAUTH_ACCOUNT_NOT_VERIFIED", status.HTTP_403_FORBIDDEN)

        # Mark this request with the provider so the manager's on_after_register
        # provisions a *new* OAuth user as external (null password) and picks its
        # role. Ignored when the login links to an existing account.
        setattr(request.state, OAUTH_REGISTRATION_REQUEST_FLAG, provider)
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
            return refuse_login(request, "OAUTH_USER_ALREADY_EXISTS")

        if not user.is_active:
            return refuse_login(request, "LOGIN_BAD_CREDENTIALS")

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
