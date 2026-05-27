"""Bearer token endpoints for mobile/API clients.

Provides email+password → access_token + refresh_token, refresh, and revoke
flows for clients that cannot use browser cookies (mobile apps, CLI tools,
third-party API consumers).
"""

from __future__ import annotations

import uuid as uuid_mod
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from simple_module_db.deps import get_db
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

from users.models import User
from users.models.refresh_token import RefreshToken

router = APIRouter(prefix="/auth", tags=["users-token"])


class TokenRequest(SQLModel):
    """Email + password login for bearer-token auth."""

    email: str
    password: str


class TokenResponse(SQLModel):
    """Access + refresh token pair returned on successful auth."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
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

    stmt = select(User).where(User.email == body.email)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user is None or not user.is_active or user.disabled_at is not None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    helper = PasswordHelper()
    verified, _ = helper.verify_and_update(body.password, user.hashed_password)
    if not verified:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    settings = request.app.state.users.settings
    return await _create_token_pair(db, user.id, settings)


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
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    now = datetime.now(timezone.utc)
    stmt = select(RefreshToken).where(
        RefreshToken.token == token_uuid,
        RefreshToken.revoked_at.is_(None),  # type: ignore[union-attr]
        RefreshToken.expires_at > now,
    )
    rt = (await db.execute(stmt)).scalar_one_or_none()
    if rt is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    rt.revoked_at = now
    await db.flush()

    settings = request.app.state.users.settings
    return await _create_token_pair(db, rt.user_id, settings)


@router.delete("/token")
async def token_revoke(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Revoke a refresh token (idempotent)."""
    try:
        token_uuid = uuid_mod.UUID(body.refresh_token)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid token format")

    stmt = select(RefreshToken).where(RefreshToken.token == token_uuid)
    rt = (await db.execute(stmt)).scalar_one_or_none()
    if rt and rt.revoked_at is None:
        rt.revoked_at = datetime.now(timezone.utc)
        await db.flush()
    return {"status": "ok"}


async def _create_token_pair(
    db: AsyncSession,
    user_id: uuid_mod.UUID,
    settings,
) -> TokenResponse:
    """Mint a new access token + refresh token pair and persist both."""
    from users.models import UserAccessToken

    now = datetime.now(timezone.utc)

    access_token = UserAccessToken(
        token=str(uuid_mod.uuid4()),
        user_id=user_id,
        created_at=now,
    )
    db.add(access_token)

    refresh = RefreshToken(
        token=uuid_mod.uuid4(),
        user_id=user_id,
        created_at=now,
        expires_at=now + timedelta(seconds=settings.refresh_token_lifetime_seconds),
    )
    db.add(refresh)
    await db.flush()

    return TokenResponse(
        access_token=access_token.token,
        refresh_token=str(refresh.token),
        token_type="bearer",
        expires_in=settings.bearer_token_lifetime_seconds,
    )
