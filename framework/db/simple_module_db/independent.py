"""A session opened outside the request, with the commit convention in one place."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def independent_session(app: Any) -> AsyncGenerator[AsyncSession]:
    """Open a session from ``app``'s factory, outside any request.

    Commits when the block exits cleanly and rolls back (then re-raises) when it
    raises, so startup hooks, background cleanups and out-of-band writes do not
    each hand-roll the pair. The session is closed either way.

    Request code must not use this: the request session (``get_db``) commits in
    ``CommitBeforeResponseMiddleware``, and a second session cannot see its
    uncommitted rows. Code that must commit mid-block, never commit, or run on a
    different engine keeps using ``session_factory()`` directly.
    """
    async with app.state.sm.db.session_factory() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
