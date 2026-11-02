"""Revoke an account's browser sessions and bearer credentials together."""

from datetime import UTC, datetime

from fastapi import FastAPI
from simple_module_db.callbacks import register_on_commit
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from users.models import RefreshToken, User, UserAccessToken
from users.session_revocation import bump_session_version, publish_revocation
from users.session_version_cache import forget_session_version


async def revoke_all_credentials(db: AsyncSession, user: User, app: FastAPI | None) -> None:
    """Strand every session and bearer credential *user* holds (password change,
    reset, "sign out everywhere"; #686).

    Bumping ``session_version`` strands browser sessions and stamped tokens, but
    the rows go too: a stolen refresh token would otherwise keep minting fresh
    access tokens until its own deadline.

    Every worker caches the counter, so the cache is evicted on commit, never
    inline: clearing before the row is durable lets a failed commit repopulate
    the *old* value and quietly re-admit everything. Other workers hear about
    it over the invalidation bus at once where a transport is installed,
    otherwise when their own entry expires (GH #318).
    """
    await revoke_credential_rows(db, user)
    user_id = user.id
    register_on_commit(db, lambda: announce_revocation(app, user_id))


async def revoke_credential_rows(db: AsyncSession, user: User) -> None:
    """Bump the session counter and revoke or delete every bearer credential."""
    await bump_session_version(db, user)
    await db.execute(
        update(RefreshToken)
        .where(col(RefreshToken.user_id) == user.id, col(RefreshToken.revoked_at).is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await db.execute(delete(UserAccessToken).where(col(UserAccessToken.user_id) == user.id))
    await db.flush()


async def announce_revocation(app: FastAPI | None, user_id) -> None:
    """Evict cached counters everywhere; call only once the revocation is durable."""
    if app is None:
        forget_session_version(user_id)
    else:
        await publish_revocation(app, user_id)
