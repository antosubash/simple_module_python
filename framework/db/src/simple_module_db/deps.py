"""FastAPI dependencies for database access."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from simple_module_db.session import get_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session, auto-closing on exit.

    Usage in FastAPI endpoints::

        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
