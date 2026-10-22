"""REST endpoints for local-credential auth + self profile.

Routes owned here (all mounted by :meth:`UsersModule.register_routes`):
  POST /api/users/auth/login          — lockout-guarded wrapper around fastapi-users
  POST /api/users/auth/logout         — clears the access-token cookie and session
  POST /api/users/auth/accept-invite  — verify invite + set password + login
  GET  /api/users/me                  — current user
  PATCH /api/users/me                 — update current user
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users import exceptions as fu_exceptions
from simple_module_core.redirect_safety import SESSION_NEXT_KEY
from simple_module_db.deps import get_db
from simple_module_hosting.session import SESSION_REMEMBER_KEY, stamp_session_expiry
from simple_module_hosting.token_guard import Authenticated
from sqlalchemy.ext.asyncio import AsyncSession

from users.auth_local.lockout import (
    admit,
    login_attempt,
    record_failure,
    record_success,
    release,
)
from users.auth_local.rate_limit import enforce_auth_throughput_limit
from users.auth_local.self_account import router as self_account_router
from users.backend import build_cookie_transport, build_strategy
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

# Re-exported: ``users.module`` mounts the stock routers with
# ``auth_local_api.enforce_auth_throughput_limit``, and the dependency moved
# down to ``rate_limit`` so ``self_account`` can import it without a cycle.
__all__ = ["enforce_auth_throughput_limit", "router"]


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

    Every part of the credential has to move together, or the checkbox lies at
    whichever expires first: the ``sm_auth`` cookie, the access-token row
    behind it, and the session cookie the pages actually authenticate with.
    This handles the first two; the session cookie is widened by recording the
    window in the session itself (see :func:`login`). Neither the transport nor
    the strategy can be varied per request on the shared backend — one
    ``CookieTransport``, one lifetime — so this builds a second pair rather
    than mutating singletons that concurrent requests are reading.
    """
    settings = request.app.state.users.settings
    window = settings.remember_me_max_age_seconds
    strategy = build_strategy(access_token_db, window)
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
    db: AsyncSession = Depends(get_db),
):
    """Lockout-guarded login wrapper. Sets sm_auth cookie + session user_id."""
    attempt = login_attempt(request, credentials.username)
    admission = await admit(db, attempt)

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
        locked = await record_failure(db, attempt, admission)
        raise locked or HTTPException(status_code=400, detail="LOGIN_BAD_CREDENTIALS")

    if not user.is_verified and request.app.state.users.settings.require_verification:
        # Match fastapi-users' own behavior when requires_verification=True.
        # With the setting off nobody is asked to verify (#547) — including
        # accounts that signed up while it was on.
        await release(db, attempt, admission)
        raise HTTPException(status_code=400, detail="LOGIN_USER_NOT_VERIFIED")

    await record_success(db, attempt, admission)
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
    if credentials.remember:
        # Recorded *in the session*, not on this response's scope. Resolving
        # the signed-in user caches its context in the session, so almost every
        # later request re-emits the cookie — and a window known only to the
        # sign-in response would be rolled back to the default by the first
        # page load after it. The session middleware reads this key each time
        # it writes the cookie.
        window = request.app.state.users.settings.remember_me_max_age_seconds
        request.session[SESSION_REMEMBER_KEY] = window
        # ``on_after_login`` already bounded this session at the default
        # window; the checkbox is what widens it. Re-stamped here rather than
        # branched inside the hook so the OAuth and accept-invite paths, which
        # have no checkbox, keep the default without knowing this exists.
        stamp_session_expiry(request.session, window)
    # The deep link has served its purpose; leaving it would send the *next*
    # plain visit to /users/login off to a stale destination.
    request.session.pop(SESSION_NEXT_KEY, None)
    return login_response


# ── Logout ───────────────────────────────────────────────────────────────────

# The stock fastapi-users auth router is deliberately not mounted: its login
# sits outside the lockout above (GH #530), and nothing called its logout.


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
            UserUpdate(**changes),  # ty: ignore[invalid-argument-type]
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


@router.get("/me", response_model=UserRead, dependencies=[Depends(Authenticated())])
async def read_me(user=Depends(fastapi_users.current_user(active=True))):
    """Return the currently authenticated user's profile."""
    return user


@router.patch("/me", response_model=UserRead, dependencies=[Depends(Authenticated())])
async def update_me(
    data: SelfProfileUpdate,
    request: Request,
    user=Depends(fastapi_users.current_user(active=True)),
    user_manager: UserManager = Depends(get_user_manager),
):
    """Update the currently authenticated user's profile."""
    return await user_manager.update(
        UserUpdate(**data.model_dump(exclude_unset=True)),  # ty: ignore[invalid-argument-type]
        user,
        request=request,
    )


# ── Self password + session revocation ───────────────────────────────────────

# Their own module: this file is at the 300-line cap, and changing your own
# password has nothing in common with the login wrappers above beyond the
# ``/me`` prefix. Mounted here so both keep that prefix and this file stays the
# one place the module's auth routes are listed.
router.include_router(self_account_router)
