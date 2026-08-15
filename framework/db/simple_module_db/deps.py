"""FastAPI dependencies for database access."""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from simple_module_db.transaction import (
    SESSION_START_KEY,
    finalize_session,
    register_request_session,
    rollback_session,
)


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session, auto-closing on exit.

    Commits only when the session has pending writes (``new``, ``dirty``,
    or ``deleted`` objects); read-only handlers exit via ``rollback``.

    The commit itself normally happens in
    :class:`~simple_module_db.transaction.CommitBeforeResponseMiddleware`,
    which fires while the response is still in the server's hands. The
    finalize below is the fallback for when that middleware isn't in the
    stack, and a no-op when it already ran — FastAPI runs this exit code
    *after* the response has been delivered, so a client that immediately
    reads back what it just wrote would otherwise race the commit and lose
    (GH #257).

    Usage in FastAPI endpoints::

        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    factory = request.app.state.sm.db.session_factory
    async with factory() as session:
        session.info[SESSION_START_KEY] = time.perf_counter()
        register_request_session(request.scope, session)
        try:
            yield session
            await finalize_session(session)
        except Exception:
            await rollback_session(session)
            raise
