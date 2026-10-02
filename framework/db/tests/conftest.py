"""Shared fixtures and test models for the database test suite."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from _models import _TenantBase
from simple_module_db.listeners import register_listeners
from simple_module_db.session import init_db
from simple_module_test.database import database_url_for_tests, init_db_kwargs, reset_schema
from sqlalchemy.ext.asyncio import AsyncSession

_URL = database_url_for_tests()


async def _tenant_session(
    *, strict: bool, default_tenant: str | None = None
) -> AsyncGenerator[AsyncSession, None]:
    db_state = init_db(_URL, **init_db_kwargs(_URL))
    db_state.tenant_strict = strict
    if default_tenant:
        db_state.default_tenant_id = default_tenant
    try:
        register_listeners(db_state)
        await reset_schema(db_state.engine)
        async with db_state.engine.begin() as conn:
            await conn.run_sync(_TenantBase.metadata.create_all)
        async with db_state.session_factory() as session:
            yield session
    finally:
        db_state.tenant_strict = False
        await db_state.engine.dispose()


@pytest.fixture
async def tenant_session() -> AsyncGenerator[AsyncSession, None]:
    """Session backed by in-memory SQLite with tenant listeners registered."""
    async for session in _tenant_session(strict=False):
        yield session


@pytest.fixture
async def strict_session() -> AsyncGenerator[AsyncSession, None]:
    """Like ``tenant_session``, with fail-closed isolation (``multi_tenant`` on)."""
    async for session in _tenant_session(strict=True):
        yield session


@pytest.fixture
async def acme_default_session() -> AsyncGenerator[AsyncSession, None]:
    """Single-tenant install with ``default_tenant="acme"``."""
    async for session in _tenant_session(strict=False, default_tenant="acme"):
        yield session
