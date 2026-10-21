"""paginate carries execution options to the count; huge pages never reach OFFSET."""

from __future__ import annotations

from _models import _TenantItem, _TenantSoftItem
from simple_module_db import PageParams, paginate, tenant_context
from simple_module_db.pagination import MAX_PAGE
from sqlalchemy import select


async def test_count_honours_include_deleted(strict_session):
    with tenant_context("a"):
        keep, gone = _TenantSoftItem(name="keep"), _TenantSoftItem(name="gone")
        strict_session.add_all([keep, gone])
        await strict_session.flush()
        await strict_session.delete(gone)
        await strict_session.flush()
        base = select(_TenantSoftItem).order_by(_TenantSoftItem.id)
        hidden = await paginate(strict_session, base, PageParams())
        shown = await paginate(
            strict_session, base.execution_options(include_deleted=True), PageParams()
        )
    assert (hidden.total, len(hidden.items)) == (1, 1)
    assert (shown.total, len(shown.items)) == (2, 2)


async def test_count_honours_all_tenants(strict_session):
    for tenant in ("a", "b"):
        with tenant_context(tenant):
            strict_session.add(_TenantItem(name=tenant))
            await strict_session.flush()
    stmt = select(_TenantItem).order_by(_TenantItem.id).execution_options(all_tenants=True)
    page = await paginate(strict_session, stmt, PageParams())
    assert (page.total, len(page.items)) == (2, 2)


def test_page_is_bounded():
    assert PageParams(page=10**15).page == MAX_PAGE


async def test_paginate_huge_page_serves_last_page(strict_session):
    with tenant_context("a"):
        strict_session.add_all([_TenantItem(name=str(i)) for i in range(3)])
        await strict_session.flush()
        stmt = select(_TenantItem).order_by(_TenantItem.id)
        page = await paginate(strict_session, stmt, PageParams(page=10**15, per_page=2))
    assert (page.page, len(page.items)) == (2, 1)
