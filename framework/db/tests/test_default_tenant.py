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
    tenant_context,
)
from sqlalchemy import insert, select
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
