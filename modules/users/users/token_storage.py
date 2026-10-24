"""Hash bearer secrets and bound opportunistic credential cleanup."""

import hashlib
import uuid
from datetime import datetime

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from users.models import RefreshToken, UserAccessToken

_PRUNE_BATCH_SIZE = 100


def hash_token(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


async def revoke_access_token(db: AsyncSession, secret: str | None) -> None:
    """Delete the access-token row behind a presented cookie, so logging out
    ends that credential server-side instead of leaving it valid until expiry."""
    if secret:
        await db.execute(
            delete(UserAccessToken).where(col(UserAccessToken.token) == hash_token(secret))
        )


async def prune_tokens(db: AsyncSession, user_id: uuid.UUID, now: datetime) -> None:
    """Prune this user's spent rows, preserving active families' reuse evidence."""
    active_families = select(RefreshToken.family_id).where(
        col(RefreshToken.user_id) == user_id,
        col(RefreshToken.revoked_at).is_(None),
        col(RefreshToken.expires_at) > now,
    )
    refresh_ids = (
        select(RefreshToken.token)
        .where(
            col(RefreshToken.user_id) == user_id,
            or_(col(RefreshToken.expires_at) <= now, col(RefreshToken.revoked_at).is_not(None)),
            col(RefreshToken.family_id).not_in(active_families),
        )
        .limit(_PRUNE_BATCH_SIZE)
    )
    await db.execute(delete(RefreshToken).where(col(RefreshToken.token).in_(refresh_ids)))
    access_ids = (
        select(UserAccessToken.token)
        .where(col(UserAccessToken.user_id) == user_id, col(UserAccessToken.expires_at) <= now)
        .limit(_PRUNE_BATCH_SIZE)
    )
    await db.execute(delete(UserAccessToken).where(col(UserAccessToken.token).in_(access_ids)))
