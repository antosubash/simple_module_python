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

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users import exceptions as fu_exceptions

from users.auth_local.rate_limit import LoginRateLimiter, ThroughputLimiter
from users.constants import SESSION_USER_ID_KEY
from users.contracts.schemas import (
    AcceptInviteRequest,
    SelfProfileUpdate,
    UserRead,
    UserUpdate,
)
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


@router.post("/auth/login", status_code=204)
async def login(
    request: Request,
    response: Response,
    credentials: OAuth2PasswordRequestForm = Depends(),
    user_manager: UserManager = Depends(get_user_manager),
    strategy=Depends(auth_backend.get_strategy),
    limiter: LoginRateLimiter = Depends(get_rate_limiter),
):
    """Rate-limited login wrapper. Sets sm_auth cookie + session user_id."""
    key = f"{credentials.username.lower()}::{request.client.host if request.client else 'unknown'}"
    if limiter.is_locked(key):
        raise HTTPException(status_code=429, detail="Too many attempts — try again later")

    try:
        user = await user_manager.authenticate(credentials)
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
    login_response = await auth_backend.login(strategy, user)
    # Bridge the session cookie — AuthMiddleware reads this to identify the user
    request.session[SESSION_USER_ID_KEY] = str(user.id)
    return login_response


# ── Mount fastapi-users stock routers ────────────────────────────────────────

# The stock auth router (login + logout) is mounted at /auth-inner so its
# logout and other endpoints remain accessible. Our wrapper at /auth/login
# shadows the stock login endpoint. Logout is exposed via /auth-inner/logout.
auth_inner = fastapi_users.get_auth_router(auth_backend, requires_verification=True)
router.include_router(auth_inner, prefix="/auth-inner")


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

    try:
        await user_manager.update(
            UserUpdate(password=body.password),
            user,
            request=request,
        )
    except fu_exceptions.InvalidPasswordException as e:
        raise HTTPException(status_code=400, detail=f"INVALID_PASSWORD: {e.reason}") from e

    await user_manager.on_after_login(user, request, response)
    login_response = await auth_backend.login(strategy, user)
    request.session[SESSION_USER_ID_KEY] = str(user.id)
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
