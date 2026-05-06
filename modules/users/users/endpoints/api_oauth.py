"""OAuth/OIDC login routes — one pair (``/login``, ``/callback``) per provider.

Why a custom handler rather than ``fastapi_users.get_oauth_router``: the stock
router's ``/callback`` returns a 204 No Content with the auth cookie set. That
works for SPA flows that redirect on a successful AJAX response, but Inertia
expects the user's browser to land on a real page. Here ``/callback`` returns
a 303 redirect to ``settings.login_redirect_url`` instead, with the same
cookie attached.

Find-or-create + email-association logic still goes through
``UserManager.oauth_callback`` — we don't reimplement it, only the transport
around it. State CSRF uses Starlette's signed session cookie (already mounted
by the framework) instead of fastapi-users' separate JWT-state cookie.
"""

from __future__ import annotations

import logging
import secrets
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi_users import exceptions as fu_exceptions
from starlette.responses import RedirectResponse

from users.deps import auth_backend, get_user_manager
from users.oauth import OAuthProvider, build_clients

if TYPE_CHECKING:
    from users.manager import UserManager
    from users.settings import UsersSettings

logger = logging.getLogger(__name__)

_SESSION_STATE_KEY_FMT = "oauth_state:{provider}"


def _build_provider_router(provider: OAuthProvider, login_redirect_url: str) -> APIRouter:
    """Mount /login + /callback for one provider."""
    router = APIRouter()
    state_key = _SESSION_STATE_KEY_FMT.format(provider=provider.name)

    @router.get("/login")
    async def begin(request: Request) -> RedirectResponse:
        """Generate a state nonce, stash it in the session, redirect to the IdP."""
        state = secrets.token_urlsafe(32)
        request.session[state_key] = state
        callback_url = str(request.url_for(f"oauth_{provider.name}_callback"))
        authorization_url = await provider.client.get_authorization_url(callback_url, state)
        return RedirectResponse(authorization_url, status_code=302)

    @router.get("/callback", name=f"oauth_{provider.name}_callback")
    async def callback(
        request: Request,
        code: str | None = None,
        state: str | None = None,
        user_manager: UserManager = Depends(get_user_manager),
        strategy=Depends(auth_backend.get_strategy),
    ) -> RedirectResponse:
        """Verify state, exchange code, find-or-create user, set cookie, redirect."""
        expected_state = request.session.pop(state_key, None)
        if not state or not expected_state or not secrets.compare_digest(state, expected_state):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="OAUTH_INVALID_STATE"
            )
        if not code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="OAUTH_MISSING_CODE"
            )

        callback_url = str(request.url_for(f"oauth_{provider.name}_callback"))
        token = await provider.client.get_access_token(code, callback_url)
        account_id, account_email = await provider.client.get_id_email(token["access_token"])
        if account_email is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAUTH_NO_EMAIL")

        try:
            user = await user_manager.oauth_callback(
                provider.name,
                token["access_token"],
                account_id,
                account_email,
                token.get("expires_at"),
                token.get("refresh_token"),
                request,
                associate_by_email=True,
                is_verified_by_default=True,
            )
        except fu_exceptions.UserAlreadyExists:
            # Email exists but associate_by_email=False would forbid linking.
            # We always pass True above, so this branch only fires if the
            # provider returns ambiguous data.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OAUTH_USER_ALREADY_EXISTS",
            ) from None

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="LOGIN_BAD_CREDENTIALS"
            )

        # Set the auth cookie via the existing backend, then bridge the
        # session in on_after_login (sets session["user_id"] for AuthMiddleware).
        login_response = await auth_backend.login(strategy, user)
        await user_manager.on_after_login(user, request, login_response)

        redirect = RedirectResponse(login_redirect_url, status_code=303)
        for key, value in login_response.headers.items():
            if key.lower() == "set-cookie":
                redirect.raw_headers.append((b"set-cookie", value.encode("latin-1")))
        return redirect

    return router


def register_oauth_routes(api_router: APIRouter, settings: UsersSettings) -> None:
    """Mount /auth/<provider>/{login,callback} for every configured provider."""
    providers = build_clients(settings)
    for provider in providers:
        api_router.include_router(
            _build_provider_router(provider, settings.login_redirect_url),
            prefix=f"/auth/{provider.name}",
            tags=["users-auth"],
        )
    if providers:
        logger.info(
            "Registered %d OAuth provider(s): %s",
            len(providers),
            ", ".join(p.name for p in providers),
        )
