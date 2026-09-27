"""Tenant rules for bulk DML, the identity map, and nested bypass blocks.

Regressions from the adversarial QA pass on the tenancy work: every test here
failed (i.e. the leak reproduced) before the fix.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from _models import _TenantBase, _TenantItem
from simple_module_db import TenantIsolationError, all_tenants, tenant_context
from simple_module_db.listeners import register_listeners
from simple_module_db.session import init_db
from simple_module_test.database import database_url_for_tests, init_db_kwargs, reset_schema
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

_URL = database_url_for_tests()


async def _session(strict: bool, *, fresh: bool = True) -> tuple:
    state = init_db(_URL, **init_db_kwargs(_URL))
    state.tenant_strict = strict
    register_listeners(state)
    if fresh:  # on Postgres the second state shares the first one's database
        await reset_schema(state.engine)
    async with state.engine.begin() as conn:
        await conn.run_sync(_TenantBase.metadata.create_all)
    return state, state.session_factory()


@pytest.fixture
async def strict_session() -> AsyncGenerator[AsyncSession, None]:
    state, session = await _session(strict=True)
    async with session:
        yield session
    await state.engine.dispose()


async def _seed(session: AsyncSession) -> None:
    for tenant in ("a", "b"):
        with tenant_context(tenant):
            session.add(_TenantItem(name=f"item-{tenant}"))
            await session.flush()


async def _names(session: AsyncSession) -> list[str]:
    with all_tenants():
        rows = (await session.execute(select(_TenantItem).order_by(_TenantItem.name))).scalars()
        return [f"{r.tenant_id}:{r.name}" for r in rows]


async def test_tenant_context_inside_all_tenants_is_scoped(strict_session: AsyncSession):
    await _seed(strict_session)
    with all_tenants(), tenant_context("a"):
        rows = (await strict_session.execute(select(_TenantItem))).scalars().all()
        await strict_session.execute(update(_TenantItem).values(name="renamed"))
    assert [r.tenant_id for r in rows] == ["a"]
    assert await _names(strict_session) == ["b:item-b", "a:renamed"]


async def test_bulk_update_cannot_assign_tenant_id(strict_session: AsyncSession):
    await _seed(strict_session)
    with tenant_context("a"), pytest.raises(TenantIsolationError):
        await strict_session.execute(update(_TenantItem).values(tenant_id="b"))


async def test_identity_map_object_cannot_be_written_from_another_tenant(
    strict_session: AsyncSession,
):
    await _seed(strict_session)
    with tenant_context("b"):
        foreign = (await strict_session.execute(select(_TenantItem))).scalar_one()
    with tenant_context("a"):
        same = await strict_session.get(_TenantItem, foreign.id)  # identity-map hit, no SQL
        same.name = "hijacked"
        with pytest.raises(TenantIsolationError, match="of tenant 'b' in context of tenant 'a'"):
            await strict_session.flush()
    await strict_session.rollback()


async def test_identity_map_object_cannot_be_deleted_from_another_tenant(
    strict_session: AsyncSession,
):
    await _seed(strict_session)
    with tenant_context("b"):
        foreign = (await strict_session.execute(select(_TenantItem))).scalar_one()
    with tenant_context("a"):
        await strict_session.delete(foreign)
        with pytest.raises(TenantIsolationError):
            await strict_session.flush()
    await strict_session.rollback()


@pytest.mark.parametrize("form", ["params", "values"])
async def test_bulk_insert_rejects_a_foreign_tenant(strict_session: AsyncSession, form: str):
    with tenant_context("a"), pytest.raises(TenantIsolationError):
        if form == "params":
            await strict_session.execute(insert(_TenantItem), [{"name": "x", "tenant_id": "b"}])
        else:
            await strict_session.execute(insert(_TenantItem).values(name="x", tenant_id="b"))


@pytest.mark.parametrize("form", ["params", "values"])
async def test_bulk_insert_is_stamped_with_the_bound_tenant(
    strict_session: AsyncSession, form: str
):
    """#357: bulk and Core-style ORM inserts get tenant_id like session.add()."""
    with tenant_context("a"):
        if form == "params":
            await strict_session.execute(insert(_TenantItem), [{"name": "x"}, {"name": "y"}])
        else:
            await strict_session.execute(insert(_TenantItem).values(name="x"))
    assert all(n.startswith("a:") for n in await _names(strict_session))


async def test_bulk_insert_without_tenant_fails_closed(strict_session: AsyncSession):
    with pytest.raises(TenantIsolationError, match="INSERT"):
        await strict_session.execute(insert(_TenantItem), [{"name": "x"}])


async def test_second_database_state_does_not_disable_strict_mode(
    strict_session: AsyncSession,
):
    await _seed(strict_session)
    other_state, other_session = await _session(strict=False, fresh=False)
    try:
        with pytest.raises(TenantIsolationError):
            await strict_session.execute(select(_TenantItem))
        async with other_session:  # the non-strict state stays non-strict
            await other_session.execute(select(_TenantItem))
    finally:
        await other_state.engine.dispose()
