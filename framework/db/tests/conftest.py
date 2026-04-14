"""Shared fixtures and test models for the database test suite."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from simple_module_db.base import create_module_base
from simple_module_db.listeners import register_listeners
from simple_module_db.mixins import MultiTenantMixin, SoftDeleteMixin
from simple_module_db.provider import DatabaseProvider
from simple_module_db.session import init_db
from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

_TenantBase = create_module_base("mt_test", provider=DatabaseProvider.SQLITE)


class _TenantItem(_TenantBase, MultiTenantMixin):  # ty: ignore[unsupported-base]
    __tablename__ = "mt_test_item"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))


class _TenantSoftItem(_TenantBase, MultiTenantMixin, SoftDeleteMixin):  # ty: ignore[unsupported-base]
    """Combines multi-tenant and soft-delete mixins to test filter composition."""

    __tablename__ = "mt_test_soft_item"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))


@pytest.fixture
async def tenant_session() -> AsyncGenerator[AsyncSession, None]:
    """Session backed by in-memory SQLite with tenant listeners registered."""
    db_state = init_db("sqlite+aiosqlite:///:memory:")
    try:
        register_listeners(db_state)
        async with db_state.engine.begin() as conn:
            await conn.run_sync(_TenantBase.metadata.create_all)
        async with db_state.session_factory() as session:
            yield session
    finally:
        await db_state.engine.dispose()
