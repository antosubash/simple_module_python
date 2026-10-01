"""Single-tenant installs: an unbound insert lands in ``DEFAULT_TENANT_ID`` (#380).

``MultiTenantMixin.tenant_id`` is NOT NULL, so before #380 the first module to
adopt the mixin broke every install with ``multi_tenant`` off. Strict mode must
keep failing closed — see ``test_tenant_strict.py``.
"""

from __future__ import annotations

import pytest
from _models import _TenantItem
from simple_module_db import (
    DEFAULT_TENANT_ID,
    TenantIsolationError,
    all_tenants,
    current_tenant_id,
    tenant_context,
)
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


def test_default_tenant_id_is_a_valid_tenant_id():
    from simple_module_db import is_valid_tenant_id

    assert DEFAULT_TENANT_ID == "default"
    assert is_valid_tenant_id(DEFAULT_TENANT_ID)


async def test_session_add_without_tenant_stamps_default(tenant_session: AsyncSession):
    item = _TenantItem(name="single")
    tenant_session.add(item)
    await tenant_session.flush()
    assert item.tenant_id == DEFAULT_TENANT_ID


async def test_explicit_tenant_id_is_kept_when_unbound(tenant_session: AsyncSession):
    item = _TenantItem(name="explicit", tenant_id="other")
    tenant_session.add(item)
    await tenant_session.flush()
    assert item.tenant_id == "other"


async def test_bound_tenant_still_wins(tenant_session: AsyncSession):
    with tenant_context("acme"):
        item = _TenantItem(name="bound")
        tenant_session.add(item)
        await tenant_session.flush()
    assert item.tenant_id == "acme"


async def test_all_tenants_block_on_single_tenant_install_stamps_default(
    tenant_session: AsyncSession,
):
    with all_tenants():
        item = _TenantItem(name="platform")
        tenant_session.add(item)
        await tenant_session.flush()
    assert item.tenant_id == DEFAULT_TENANT_ID


async def test_orm_insert_values_stamps_default(tenant_session: AsyncSession):
    await tenant_session.execute(insert(_TenantItem).values(name="core-one"))
    await tenant_session.execute(insert(_TenantItem), [{"name": "bulk-a"}, {"name": "bulk-b"}])
    await tenant_session.execute(insert(_TenantItem).values([{"name": "mv-a"}, {"name": "mv-b"}]))
    await tenant_session.execute(insert(_TenantItem.__table__).values(name="table"))
    rows = (await tenant_session.execute(select(_TenantItem))).scalars().all()
    assert len(rows) == 6
    assert {r.tenant_id for r in rows} == {DEFAULT_TENANT_ID}


async def test_unbound_reads_stay_unfiltered(tenant_session: AsyncSession):
    """Not strict + no tenant reads every row — the single-tenant semantics."""
    tenant_session.add(_TenantItem(name="default-row"))
    tenant_session.add(_TenantItem(name="other-row", tenant_id="other"))
    await tenant_session.flush()
    rows = (await tenant_session.execute(select(_TenantItem))).scalars().all()
    assert {r.name for r in rows} == {"default-row", "other-row"}


async def test_strict_mode_does_not_fall_back(strict_session: AsyncSession):
    strict_session.add(_TenantItem(name="orphan"))
    with pytest.raises(TenantIsolationError, match="INSERT"):
        await strict_session.flush()
    await strict_session.rollback()
    with pytest.raises(TenantIsolationError, match="INSERT"):
        await strict_session.execute(insert(_TenantItem).values(name="orphan"))


async def _insert_all_shapes(session: AsyncSession) -> set[str]:
    session.add(_TenantItem(name="added"))
    await session.flush()
    await session.execute(insert(_TenantItem).values(name="core-one"))
    await session.execute(insert(_TenantItem), [{"name": "bulk-a"}])
    await session.execute(insert(_TenantItem).values([{"name": "mv-a"}]))
    await session.execute(insert(_TenantItem.__table__).values(name="table"))
    stmt = select(_TenantItem).execution_options(all_tenants=True)
    return {r.tenant_id for r in (await session.execute(stmt)).scalars().all()}


async def test_bypassed_insert_with_a_bound_tenant_keeps_the_bound_tenant(
    tenant_session: AsyncSession,
):
    """``execution_options(all_tenants=True)`` widens a statement's scope; a
    missing ``tenant_id`` still goes to the bound tenant, not the fallback."""
    with tenant_context("acme"):
        for stmt in (
            insert(_TenantItem).values(name="core"),
            insert(_TenantItem).values([{"name": "mv"}]),
            insert(_TenantItem.__table__).values(name="table"),
        ):
            await tenant_session.execute(stmt.execution_options(all_tenants=True))
        await tenant_session.execute(
            insert(_TenantItem).execution_options(all_tenants=True), [{"name": "bulk"}]
        )
    stmt = select(_TenantItem).execution_options(all_tenants=True)
    rows = (await tenant_session.execute(stmt)).scalars().all()
    assert len(rows) == 4
    assert {r.tenant_id for r in rows} == {"acme"}


async def test_flush_in_bypass_with_a_bound_tenant_keeps_the_bound_tenant(
    tenant_session: AsyncSession,
):
    """``all_tenants()`` clears the tenant, but code that binds one inside the
    bypass (a restored context, ``bind_current_tenant``) keeps its writes."""
    with all_tenants():
        token = current_tenant_id.set("acme")
        try:
            item = _TenantItem(name="added")
            tenant_session.add(item)
            await tenant_session.flush()
        finally:
            current_tenant_id.reset(token)
    assert item.tenant_id == "acme"


async def test_default_tenant_install_stamps_it_when_unbound(
    acme_default_session: AsyncSession,
):
    assert await _insert_all_shapes(acme_default_session) == {"acme"}


async def test_default_tenant_install_stamps_it_inside_all_tenants(
    acme_default_session: AsyncSession,
):
    with all_tenants():
        assert await _insert_all_shapes(acme_default_session) == {"acme"}


async def test_plain_install_stamps_default_inside_all_tenants(tenant_session: AsyncSession):
    with all_tenants():
        assert await _insert_all_shapes(tenant_session) == {DEFAULT_TENANT_ID}


async def test_strict_bypass_leaves_missing_tenant_to_the_database(
    strict_session: AsyncSession,
):
    """Strict is unchanged: an all_tenants() insert is not stamped."""
    with all_tenants():
        strict_session.add(_TenantItem(name="orphan"))
        with pytest.raises(IntegrityError):
            await strict_session.flush()
