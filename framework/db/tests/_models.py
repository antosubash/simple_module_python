"""Test-only SQLModel tables used across the database test suite.

Kept in a dedicated module so that ``from conftest import`` is not required at
module level in individual test files (which is fragile when multiple test
directories with their own ``conftest.py`` files are collected in the same
pytest run).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable

from simple_module_db.base import create_module_base
from simple_module_db.listeners import register_listeners
from simple_module_db.mixins import MultiTenantMixin, SoftDeleteMixin
from simple_module_db.session import init_db
from simple_module_test.database import database_url_for_tests, init_db_kwargs, reset_schema
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field

_URL = database_url_for_tests()

_TenantBase = create_module_base("mt_test")


class _TenantItem(_TenantBase, MultiTenantMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "mt_test_item"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)


class _TenantSoftItem(_TenantBase, MultiTenantMixin, SoftDeleteMixin, table=True):  # ty: ignore[unsupported-base]
    """Combines multi-tenant and soft-delete mixins to test filter composition."""

    __tablename__ = "mt_test_soft_item"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)


_TxnBase = create_module_base("txn_test")


class _TxnThing(_TxnBase, table=True):  # ty: ignore[unsupported-base]
    """Plain table for exercising when the request's unit of work commits."""

    __tablename__ = "txn_test_thing"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)


async def _tenant_session(
    metadata: MetaData,
    *,
    strict: bool,
    default_tenant: str | None = None,
    seed: Callable[[AsyncSession], Awaitable[None]] | None = None,
) -> AsyncGenerator[AsyncSession, None]:
    """A session over ``metadata``'s tables with tenant listeners registered.

    ``seed`` runs in its own session first, so the yielded one starts clean.
    """
    db_state = init_db(_URL, **init_db_kwargs(_URL))
    db_state.tenant_strict = strict
    if default_tenant:
        db_state.default_tenant_id = default_tenant
    try:
        register_listeners(db_state)
        await reset_schema(db_state.engine)
        async with db_state.engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
        if seed is not None:
            async with db_state.session_factory() as session:
                await seed(session)
        async with db_state.session_factory() as session:
            yield session
    finally:
        db_state.tenant_strict = False
        await db_state.engine.dispose()
