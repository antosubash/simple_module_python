"""FastAPI dependencies for database access."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from simple_module_db.listeners import SESSION_HAS_WRITES_KEY

_db_logger = logging.getLogger("simple_module.db")


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session, auto-closing on exit.

    Commits only when the session has pending writes (``new``, ``dirty``,
    or ``deleted`` objects). Read-only handlers still open an implicit
    transaction but exit via ``rollback`` — that's one round-trip
    cheaper than ``commit`` and keeps read-only queries from showing up
    as writes in query logs / ``pg_stat_statements``.

    Usage in FastAPI endpoints::

        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    factory = request.app.state.db.session_factory
    start = time.perf_counter()
    async with factory() as session:
        try:
            yield session
            # ``has_writes`` is set by the after_flush listener and
            # survives the flush emptying session.new/.dirty/.deleted.
            has_pending = bool(
                session.info.get(SESSION_HAS_WRITES_KEY)
                or session.new
                or session.dirty
                or session.deleted
            )
            if has_pending:
                await session.commit()
                op, log_message = "commit", "db.session.commit"
                log = _db_logger.info
            else:
                await session.rollback()
                op, log_message = "read_only_rollback", "db.session.read_only"
                log = _db_logger.debug
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            log(log_message, extra={"operation": op, "db_duration_ms": duration_ms})
        except Exception:
            await session.rollback()
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            _db_logger.warning(
                "db.session.rollback",
                extra={"operation": "rollback", "db_duration_ms": duration_ms},
            )
            raise
