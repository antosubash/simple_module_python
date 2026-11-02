"""Fixtures for tenant-scope flag tests, which need real tenants to name."""

from __future__ import annotations

import pytest


@pytest.fixture
def make_tenant(app):
    """``await make_tenant("acme")`` — a tenants row with that id."""

    async def make(tenant_id: str) -> str:
        from tenants.models import Tenant

        async with app.state.sm.db.session_factory() as session:
            session.add(Tenant(id=tenant_id, slug=tenant_id, name=tenant_id.title()))
            await session.commit()
        return tenant_id

    return make


@pytest.fixture
async def acme_tenant(make_tenant) -> str:
    return await make_tenant("acme")
