"""FastAPI dependencies for database access."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

_db_logger = logging.getLogger("simple_module.db")


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session, auto-closing on exit.

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
            await session.commit()
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            _db_logger.info(
                "db.session.commit",
                extra={"operation": "commit", "db_duration_ms": duration_ms},
            )
        except Exception:
            await session.rollback()
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            _db_logger.warning(
                "db.session.rollback",
                extra={"operation": "rollback", "db_duration_ms": duration_ms},
            )
            raise
