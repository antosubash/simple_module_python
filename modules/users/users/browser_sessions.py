"""Retire the current browser session and refresh the account's cached state."""

import uuid
from datetime import UTC, datetime

from auth.constants import SESSION_ID_KEY
from fastapi import Request
from simple_module_db.callbacks import register_on_commit
from simple_module_hosting.session import SESSION_EXPIRES_AT_KEY
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from users.constants import SESSION_USER_ID_KEY
from users.models import RevokedSession
from users.session_revocation import publish_revocation


async def revoke_browser_session(request: Request, db: AsyncSession) -> None:
    session = request.session
    identity = session.get(SESSION_ID_KEY)
    user_id = session.get(SESSION_USER_ID_KEY)
    if not identity or not user_id:
        return
    now = datetime.now(UTC)
    await db.execute(delete(RevokedSession).where(col(RevokedSession.expires_at) <= now))
    # Merge makes repeated logout requests for the same cookie idempotent.
    await db.merge(
        RevokedSession(
            session_id=identity,
            user_id=uuid.UUID(user_id),
            expires_at=datetime.fromtimestamp(session[SESSION_EXPIRES_AT_KEY], UTC),
        )
    )
    await db.flush()
    register_on_commit(db, lambda: publish_revocation(request.app, uuid.UUID(user_id)))
