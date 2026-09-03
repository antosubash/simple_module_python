"""REST endpoints for local-credential auth + self profile.

Routes owned here (all mounted by :meth:`UsersModule.register_routes`):
  POST /api/users/auth/login          — rate-limited wrapper around fastapi-users
  POST /api/users/auth/accept-invite  — verify invite + set password + login
  GET  /api/users/me                  — current user
  PATCH /api/users/me                 — update current user
  /api/users/auth-inner/*             — fastapi-users stock auth router
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users import exceptions as fu_exceptions
from simple_module_core.redirect_safety import SESSION_NEXT_KEY

from users.auth_local.rate_limit import LoginRateLimiter, ThroughputLimiter
from users.auth_local.self_account import router as self_account_router
from users.backend import build_cookie_transport, get_database_strategy
from users.constants import SESSION_USER_ID_KEY
from users.contracts.schemas import (
    AcceptInviteRequest,
    LoginRequest,
    SelfProfileUpdate,
    UserRead,
    UserUpdate,
)
from users.db_adapter import get_access_token_db
from users.deps import (
    auth_backend,
    fastapi_users,
    get_user_manager,
)
from users.manager import UserManager

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Rate limit ───────────────────────────────────────────────────────────────


def get_rate_limiter(request: Request) -> LoginRateLimiter:
    """Return the per-app LoginRateLimiter built in UsersModule.on_startup."""
    return request.app.state.users.rate_limiter


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def enforce_auth_throughput_limit(request: Request) -> None:
    """FastAPI dependency that rejects the request with 429 when this IP has
    exhausted its attempts budget on shared auth side-effect endpoints.

    Applied to forgot-password / register / accept-invite / request-verify-token,
    which otherwise allow unlimited email or account-creation spam.
    """
    limiter: ThroughputLimiter = request.app.state.users.auth_throughput_limiter
    key = f"{request.url.path}::{_client_ip(request)}"
    if not limiter.check_and_record(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts — try again later",
        )


async def require_signup_enabled(request: Request) -> None:
    """Gate the register endpoint at request time on ``allow_signup``.

    Mounting stays unconditional so settings reloads don't need to rebuild
    the router. When signup is disabled we return 404 so the endpoint
    appears absent (matches the view-side behaviour at ``/users/register``).
    """
    if not request.app.state.users.settings.allow_signup:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


# ── Wrapper login ────────────────────────────────────────────────────────────


async def _remembered_login_response(request: Request, user, access_token_db) -> Response:
    """Sign in for the "Keep me signed in" window instead of the default one.

    Both halves of the credential have to move together: the access token is a
    row with its own expiry and the cookie has its own ``Max-Age``, so a long
    cookie around a short token would sign the user out halfway through the
    window the checkbox promised. Neither can be varied per request on the
    shared backend — one ``CookieTransport``, one strategy lifetime — so this
    builds a second pair rather than mutating singletons that concurrent
    requests are reading.
    """
    settings = request.app.state.users.settings
    window = settings.remember_me_max_age_seconds
    strategy = get_database_strategy(access_token_db, lifetime_seconds=window)
    transport = build_cookie_transport(
        cookie_name=settings.cookie_name,
        cookie_max_age_seconds=window,
        cookie_secure=settings.cookie_secure,
        cookie_samesite=settings.cookie_samesite,
    )
    return await transport.get_login_response(await strategy.write_token(user))


@router.post("/auth/login", status_code=204)
async def login(
    request: Request,
    response: Response,
    credentials: Annotated[LoginRequest, Form()],
    user_manager: UserManager = Depends(get_user_manager),
    strategy=Depends(auth_backend.get_strategy),
    access_token_db=Depends(get_access_token_db),
    limiter: LoginRateLimiter = Depends(get_rate_limiter),
):
    """Rate-limited login wrapper. Sets sm_auth cookie + session user_id."""
    key = f"{credentials.username.lower()}::{request.client.host if request.client else 'unknown'}"
    if limiter.is_locked(key):
        raise HTTPException(status_code=429, detail="Too many attempts — try again later")

    try:
        user = await user_manager.authenticate(
            OAuth2PasswordRequestForm(
                username=credentials.username,
                password=credentials.password,
            )
        )
    except fu_exceptions.UserNotExists:
        user = None

    if user is None or not user.is_active:
        limiter.record_failure(key)
        raise HTTPException(status_code=400, detail="LOGIN_BAD_CREDENTIALS")

    if not user.is_verified:
        # Match fastapi-users' own behavior when requires_verification=True
        raise HTTPException(status_code=400, detail="LOGIN_USER_NOT_VERIFIED")

    limiter.reset(key)
    # Fire the login hook (updates last_login_at)
    await user_manager.on_after_login(user, request, response)
    # Set fastapi-users' cookie via auth_backend.login
    login_response = (
        await _remembered_login_response(request, user, access_token_db)
        if credentials.remember
        else await auth_backend.login(strategy, user)
    )
    # Bridge the session cookie — AuthMiddleware reads this to identify the user
    request.session[SESSION_USER_ID_KEY] = str(user.id)
    # The deep link has served its purpose; leaving it would send the *next*
    # plain visit to /users/login off to a stale destination.
    request.session.pop(SESSION_NEXT_KEY, None)
    return login_response


# ── Mount fastapi-users stock routers ────────────────────────────────────────

# The stock auth router (login + logout) is mounted at /auth-inner so its
# endpoints remain accessible. Our wrappers at /auth/login and /auth/logout
# shadow the stock endpoints to also manage the session cookie.
auth_inner = fastapi_users.get_auth_router(auth_backend, requires_verification=True)
router.include_router(auth_inner, prefix="/auth-inner")


@router.post("/auth/logout", status_code=204)
async def api_logout(request: Request):
    """API logout — clears both the access-token cookie and the session."""
    request.session.clear()
    cookie_name = request.app.state.users.settings.cookie_name
    response = Response(status_code=204)
    response.delete_cookie(cookie_name, path="/")
    return response


# ── Accept-invite (verify + set password + login, one shot) ─────────────────


@router.post(
    "/auth/accept-invite",
    status_code=204,
    dependencies=[Depends(enforce_auth_throughput_limit)],
)
async def accept_invite(
    body: AcceptInviteRequest,
    request: Request,
    response: Response,
    user_manager: UserManager = Depends(get_user_manager),
    strategy=Depends(auth_backend.get_strategy),
):
    """Verify an invite token, set the user's password, and log them in."""
    try:
        user = await user_manager.verify(body.token, request=request)
    except (fu_exceptions.InvalidVerifyToken, fu_exceptions.UserAlreadyVerified):
        raise HTTPException(status_code=400, detail="INVITE_BAD_TOKEN") from None

    # A blank name leaves whatever the admin typed when minting the invite
    # alone: the field is pre-filled from it, so an untouched form must not
    # read as "clear this". Omitted rather than passed as None — ``UserUpdate``
    # dumps with ``exclude_unset``, so an explicit None would write the wipe.
    changes: dict[str, str] = {"password": body.password}
    if body.full_name and body.full_name.strip():
        changes["full_name"] = body.full_name.strip()
    try:
        await user_manager.update(
            UserUpdate(**changes),
            user,
            request=request,
        )
    except fu_exceptions.InvalidPasswordException as e:
        raise HTTPException(status_code=400, detail=f"INVALID_PASSWORD: {e.reason}") from e

    await user_manager.on_after_login(user, request, response)
    login_response = await auth_backend.login(strategy, user)
    request.session[SESSION_USER_ID_KEY] = str(user.id)
    # Invite acceptance routes the user itself, so a deep link stashed by an
    # earlier bounce is stale here — drop it rather than leave it to fire on
    # some later visit to the login page.
    request.session.pop(SESSION_NEXT_KEY, None)
    return login_response


# ── Self profile ─────────────────────────────────────────────────────────────


@router.get("/me", response_model=UserRead)
async def read_me(user=Depends(fastapi_users.current_user(active=True))):
    """Return the currently authenticated user's profile."""
    return user


@router.patch("/me", response_model=UserRead)
async def update_me(
    data: SelfProfileUpdate,
    request: Request,
    user=Depends(fastapi_users.current_user(active=True)),
    user_manager: UserManager = Depends(get_user_manager),
):
    """Update the currently authenticated user's profile."""
    return await user_manager.update(
        UserUpdate(**data.model_dump(exclude_unset=True)),
        user,
        request=request,
    )


# ── Self password + session revocation ───────────────────────────────────────

# Their own module: this file is at the 300-line cap, and changing your own
# password has nothing in common with the login wrappers above beyond the
# ``/me`` prefix. Mounted here so both keep that prefix and this file stays the
# one place the module's auth routes are listed.
router.include_router(self_account_router)
