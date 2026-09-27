"""Strict (fail-closed) tenant isolation: no tenant context means no query."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from _models import _TenantBase, _TenantItem
from simple_module_db import TenantIsolationError, all_tenants, tenant_context
from simple_module_db.listeners import register_listeners
from simple_module_db.session import init_db
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def strict_session() -> AsyncGenerator[AsyncSession, None]:
    db_state = init_db("sqlite+aiosqlite:///:memory:")
    db_state.tenant_strict = True
    try:
        register_listeners(db_state)
        async with db_state.engine.begin() as conn:
            await conn.run_sync(_TenantBase.metadata.create_all)
        async with db_state.session_factory() as session:
            yield session
    finally:
        db_state.tenant_strict = False
        await db_state.engine.dispose()


async def _seed(session: AsyncSession) -> None:
    for tenant in ("a", "b"):
        with tenant_context(tenant):
            session.add(_TenantItem(name=f"item-{tenant}"))
            await session.flush()


async def test_select_without_tenant_raises(strict_session: AsyncSession):
    await _seed(strict_session)
    with pytest.raises(TenantIsolationError, match="SELECT"):
        await strict_session.execute(select(_TenantItem))


async def test_insert_without_tenant_raises_before_db(strict_session: AsyncSession):
    strict_session.add(_TenantItem(name="orphan"))
    with pytest.raises(TenantIsolationError, match="INSERT"):
        await strict_session.flush()
    await strict_session.rollback()


async def test_scoped_select_still_filters(strict_session: AsyncSession):
    await _seed(strict_session)
    with tenant_context("a"):
        rows = (await strict_session.execute(select(_TenantItem))).scalars().all()
    assert [r.name for r in rows] == ["item-a"]


async def test_bulk_update_is_scoped_to_tenant(strict_session: AsyncSession):
    await _seed(strict_session)
    with tenant_context("a"):
        await strict_session.execute(update(_TenantItem).values(name="renamed"))
    with all_tenants():
        names = (await strict_session.execute(select(_TenantItem.name))).scalars().all()
    assert sorted(names) == ["item-b", "renamed"]


async def test_bulk_delete_without_tenant_raises(strict_session: AsyncSession):
    await _seed(strict_session)
    with pytest.raises(TenantIsolationError, match="DELETE"):
        await strict_session.execute(delete(_TenantItem))


async def test_all_tenants_block_reads_everything(strict_session: AsyncSession):
    await _seed(strict_session)
    with all_tenants():
        count = await strict_session.scalar(select(func.count()).select_from(_TenantItem))
    assert count == 2


async def test_all_tenants_clears_an_active_tenant(strict_session: AsyncSession):
    await _seed(strict_session)
    with tenant_context("a"), all_tenants():
        count = await strict_session.scalar(select(func.count()).select_from(_TenantItem))
    assert count == 2


async def test_statement_option_bypasses_one_query(strict_session: AsyncSession):
    await _seed(strict_session)
    stmt = select(_TenantItem).execution_options(all_tenants=True)
    rows = (await strict_session.execute(stmt)).scalars().all()
    assert len(rows) == 2


async def test_unscoped_code_cannot_move_rows_between_tenants(strict_session: AsyncSession):
    await _seed(strict_session)
    with all_tenants():
        item = (await strict_session.execute(select(_TenantItem).limit(1))).scalar_one()
    item.tenant_id = "c"
    with pytest.raises(TenantIsolationError, match="Cannot change tenant_id"):
        await strict_session.flush()
    await strict_session.rollback()


def test_tenant_context_rejects_empty_id():
    with pytest.raises(ValueError), tenant_context(""):
        pass


@pytest.mark.parametrize("bad", ["x" * 51, "has space", "-dash-first"])
def test_tenant_context_rejects_malformed_ids(bad):
    with pytest.raises(ValueError), tenant_context(bad):
        pass
