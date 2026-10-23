"""Short-lived durable transactions, independent of the request unit of work."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from simple_module_db.callbacks import discard_on_commit_callbacks, run_on_commit_callbacks
from simple_module_db.session import SESSION_FACTORY_KEY, RequestSession


@asynccontextmanager
async def independent_session(source: Any) -> AsyncGenerator[RequestSession]:
    """Commit an independent session on success; roll back and re-raise on error.

    Accept an app or session factory. An existing session can also supply its
    framework session factory; its pending work is never transferred.
    Request code may use this for a deliberate durable checkpoint, whose writes
    must survive a later request failure. The new session cannot see pending
    request writes. Keep checkpoints short and avoid holding a write transaction
    on the same database while opening one (especially on SQLite).

    Post-commit callbacks run in registration order after the commit succeeds.
    The session closes on every exit, including cancellation.
    """
    if isinstance(source, async_sessionmaker):
        factory = source
    elif isinstance(source, AsyncSession):
        factory = source.info[SESSION_FACTORY_KEY]
    else:
        factory = source.state.sm.db.session_factory
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except BaseException as exc:
            discard_on_commit_callbacks(session)
            # Closing the session handles cancellation without masking it with
            # another cancellable await; ordinary failures roll back explicitly.
            if isinstance(exc, Exception):
                await session.rollback()
            raise
        await run_on_commit_callbacks(session)
