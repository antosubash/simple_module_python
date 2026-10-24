"""Bearer token endpoints for mobile/API clients.

Provides email+password → access_token + refresh_token, refresh, and revoke
flows for clients that cannot use browser cookies (mobile apps, CLI tools,
third-party API consumers).
"""

from __future__ import annotations

import uuid as uuid_mod
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from simple_module_db.deps import get_db
from simple_module_db.transaction import rollback_session
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, col
from starlette.responses import JSONResponse

from users.auth_local.lockout import (
    admit,
    login_attempt,
    record_failure,
    record_success,
    release,
)
from users.demo.guard import DEMO_READ_ONLY_DETAIL, is_read_only_demo
from users.models import User
from users.models.refresh_token import RefreshToken

# Pre-computed bcrypt hash used when a login attempt targets a non-existent
# user. Running verify against this takes the same time as a real check,
# preventing timing-based email enumeration.
_DUMMY_HASH = "$2b$12$LJ3m4ys3Lg/PFgWCZxEzR.ZVxFMz3yeqHEhSYmiJ9gJOPG7W3Cq2G"

router = APIRouter(prefix="/auth", tags=["users-token"])


class TokenRequest(SQLModel):
    """Email + password login for bearer-token auth."""

    email: str
    password: str


class TokenResponse(SQLModel):
    """Access + refresh token pair returned on successful auth."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


class RefreshRequest(SQLModel):
    """Body for refresh and revoke endpoints."""

    refresh_token: str


@router.post("/token", response_model=TokenResponse)
async def token_login(
    body: TokenRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Exchange email + password for an access/refresh token pair."""
    from fastapi_users.password import PasswordHelper

    helper = PasswordHelper()
    # Same lockout as the session login (GH #530): a slot is taken before the
    # password is checked, and a success gives it back.
    attempt = login_attempt(request, body.email)
    admission = await admit(db, attempt)

    # Case-insensitive, like ``UserDatabaseWithRoles.get_by_email`` behind the
    # session login, so ``Alice@X`` reaches the account it is counted against.
    stmt = select(User).where(func.lower(User.email) == body.email.lower())
    user = (await db.execute(stmt)).scalar_one_or_none()
    if (
        user is None
        or not user.is_active
        or user.disabled_at is not None
        # External (SSO) users have ``hashed_password is None`` — there's no
        # local password to verify. Treat them like a missing user: verifying
        # against a None hash would raise (500) and the instant failure would
        # leak that the account is SSO-only. The session login is guarded the
        # same way in ``UserManager.authenticate``.
        or user.hashed_password is None
    ):
        # Constant-time: run bcrypt on a dummy hash to prevent timing-based
        # email enumeration (existing user + wrong password takes ~50ms for
        # bcrypt; missing user would be instant without this).
        helper.verify_and_update(body.password, _DUMMY_HASH)
        await rollback_session(db)
        locked = await record_failure(db, attempt, admission)
        raise locked or HTTPException(status_code=401, detail="Invalid credentials")

    verified, updated_hash = helper.verify_and_update(body.password, user.hashed_password)
    if not verified:
        await rollback_session(db)
        locked = await record_failure(db, attempt, admission)
        raise locked or HTTPException(status_code=401, detail="Invalid credentials")
    settings = request.app.state.users.settings
    if is_read_only_demo(request.app, user.id):
        await rollback_session(db)
        await release(db, attempt, admission)
        raise HTTPException(status_code=403, detail=DEMO_READ_ONLY_DETAIL)
    if not user.is_verified and settings.require_verification:
        # Same rule as the session login: a self-registered account that never
        # proved its address must not mint bearer tokens either (#547).
        await rollback_session(db)
        await release(db, attempt, admission)
        raise HTTPException(status_code=400, detail="LOGIN_USER_NOT_VERIFIED")
    if updated_hash is not None:
        # A legacy-scheme hash (e.g. bcrypt) was accepted and re-hashed with the
        # current scheme; persist it, as ``UserManager.authenticate`` does for
        # the session login. ``get_db`` commits since this is a pending write.
        user.hashed_password = updated_hash
        await db.flush()

    await record_success(db, attempt, admission)
    return await _create_token_pair(db, user.id, settings, user.session_version)


@router.post("/token/refresh", response_model=TokenResponse)
async def token_refresh(
    body: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Rotate a refresh token into a new access/refresh pair."""
    try:
        token_uuid = uuid_mod.UUID(body.refresh_token)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid refresh token") from None

    now = datetime.now(UTC)
    stmt = (
        update(RefreshToken)
        .where(
            col(RefreshToken.token) == token_uuid,
            col(RefreshToken.revoked_at).is_(None),
            col(RefreshToken.expires_at) > now,
        )
        .values(revoked_at=now)
        .returning(RefreshToken)
    )
    rt = (await db.execute(stmt)).scalar_one_or_none()
    if rt is None:
        reused = (
            await db.execute(select(RefreshToken).where(col(RefreshToken.token) == token_uuid))
        ).scalar_one_or_none()
        if reused is not None and reused.revoked_at is not None:
            await db.execute(
                update(RefreshToken)
                .where(
                    col(RefreshToken.family_id) == reused.family_id,
                    col(RefreshToken.revoked_at).is_(None),
                )
                .values(revoked_at=now)
            )
        # Returning a response lets get_db commit revocations; raising rolls them back.
        return JSONResponse({"detail": "Invalid or expired refresh token"}, status_code=401)

    # The account is re-read rather than trusted from the row: a refresh token
    # outlives the access tokens it mints, so between two refreshes the user may
    # have been deactivated, or signed everything out. Minting from a stale
    # ``user_id`` alone would hand back a live credential to an account that no
    # longer has one.
    user = (await db.execute(select(User).where(col(User.id) == rt.user_id))).scalar_one_or_none()
    if user is None or not user.is_active or user.disabled_at is not None:
        return JSONResponse({"detail": "Invalid or expired refresh token"}, status_code=401)
    if is_read_only_demo(request.app, user.id):
        # A refusal must not consume the token: undo the revocation above.
        await rollback_session(db)
        raise HTTPException(status_code=403, detail=DEMO_READ_ONLY_DETAIL)

    settings = request.app.state.users.settings
    return await _create_token_pair(db, user.id, settings, user.session_version, rt.family_id)


@router.delete("/token")
async def token_revoke(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Revoke a refresh token (idempotent)."""
    try:
        token_uuid = uuid_mod.UUID(body.refresh_token)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid token format") from None

    stmt = select(RefreshToken).where(col(RefreshToken.token) == token_uuid)
    rt = (await db.execute(stmt)).scalar_one_or_none()
    if rt and rt.revoked_at is None:
        rt.revoked_at = datetime.now(UTC)
        await db.flush()
    return {"status": "ok"}


async def _create_token_pair(
    db: AsyncSession,
    user_id: uuid_mod.UUID,
    settings,
    session_version: int = 0,
    family_id: uuid_mod.UUID | None = None,
) -> TokenResponse:
    """Mint a new access token + refresh token pair and persist both.

    ``expires_at`` is stamped from ``bearer_token_lifetime_seconds`` — the same
    number this function reports as ``expires_in``. Without it the row was read
    back against the process-wide thirty-day ceiling, so a client that honoured
    ``expires_in`` re-authenticated every fifteen minutes while the token it
    discarded stayed valid for a month.
    """
    from users.models import UserAccessToken

    now = datetime.now(UTC)

    access_token = UserAccessToken(
        token=str(uuid_mod.uuid4()),
        user_id=user_id,
        created_at=now,
        expires_at=now + timedelta(seconds=settings.bearer_token_lifetime_seconds),
        session_version=int(session_version or 0),
    )
    db.add(access_token)

    refresh = RefreshToken(
        token=uuid_mod.uuid4(),
        family_id=family_id or uuid_mod.uuid4(),
        user_id=user_id,
        created_at=now,
        expires_at=now + timedelta(seconds=settings.refresh_token_lifetime_seconds),
    )
    db.add(refresh)
    await db.flush()

    return TokenResponse(
        access_token=access_token.token,
        refresh_token=str(refresh.token),
        token_type="Bearer",
        expires_in=settings.bearer_token_lifetime_seconds,
    )
