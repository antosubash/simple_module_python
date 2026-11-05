"""Retire the current browser session and refresh the account's cached state."""

import uuid
from datetime import UTC, datetime

from auth.constants import SESSION_ID_KEY
from fastapi import Request
from simple_module_db.callbacks import register_on_commit
from simple_module_hosting.session import SESSION_EXPIRES_AT_KEY, SESSION_SIGNATURE_MAX_AGE
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from users.constants import SESSION_USER_ID_KEY
from users.models import RevokedSession
from users.session_revocation import publish_revocation
from users.token_storage import revoke_access_token


async def revoke_browser_session(request: Request, db: AsyncSession) -> None:
    session = request.session
    identity = session.get(SESSION_ID_KEY)
    user_id = session.get(SESSION_USER_ID_KEY)
    if not identity or not user_id:
        return
    now = datetime.now(UTC)
    deadline = session.get(SESSION_EXPIRES_AT_KEY)
    if isinstance(deadline, bool) or not isinstance(deadline, (int, float)):
        # No usable deadline: hold the record for the longest the signer accepts.
        deadline = now.timestamp() + SESSION_SIGNATURE_MAX_AGE
    await db.execute(delete(RevokedSession).where(col(RevokedSession.expires_at) <= now))
    # Merge makes repeated logout requests for the same cookie idempotent.
    await db.merge(
        RevokedSession(
            session_id=identity,
            user_id=uuid.UUID(user_id),
            expires_at=datetime.fromtimestamp(deadline, UTC),
        )
    )
    await db.flush()
    register_on_commit(db, lambda: publish_revocation(request.app, uuid.UUID(user_id)))


async def end_browser_session(request: Request, db: AsyncSession) -> str:
    """Revoke the browser session and its access token; return the cookie name."""
    await revoke_browser_session(request, db)
    request.session.clear()
    cookie_name = request.app.state.users.settings.cookie_name
    await revoke_access_token(db, request.cookies.get(cookie_name))
    return cookie_name
