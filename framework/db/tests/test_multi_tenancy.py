"""Tests for automatic tenant isolation: auto-populate, filtering, enforcement."""

from __future__ import annotations

import asyncio

import pytest
from simple_module_db.listeners import TenantIsolationError, current_tenant_id
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from conftest import _TenantItem, _TenantSoftItem  # ty: ignore[unresolved-import]


class TestMultiTenancy:
    """Automatic tenant isolation: auto-populate, query filtering, enforcement."""

    async def test_auto_populate_tenant_id(self, tenant_session: AsyncSession):
        """New objects should get tenant_id from the current context."""
        token = current_tenant_id.set("tenant-a")
        try:
            item = _TenantItem(name="Widget")
            tenant_session.add(item)
            await tenant_session.flush()
            assert item.tenant_id == "tenant-a"
        finally:
            current_tenant_id.reset(token)

    async def test_explicit_tenant_id_preserved(self, tenant_session: AsyncSession):
        """Explicitly set tenant_id matching the context should be kept."""
        token = current_tenant_id.set("tenant-a")
        try:
            item = _TenantItem(name="Explicit", tenant_id="tenant-a")
            tenant_session.add(item)
            await tenant_session.flush()
            assert item.tenant_id == "tenant-a"
        finally:
            current_tenant_id.reset(token)

    async def test_query_returns_only_current_tenant(self, tenant_session: AsyncSession):
        """SELECT should be automatically filtered to the current tenant."""
        token_a = current_tenant_id.set("tenant-a")
        try:
            tenant_session.add_all([_TenantItem(name="A1"), _TenantItem(name="A2")])
            await tenant_session.flush()
        finally:
            current_tenant_id.reset(token_a)

        token_b = current_tenant_id.set("tenant-b")
        try:
            tenant_session.add(_TenantItem(name="B1"))
            await tenant_session.flush()
        finally:
            current_tenant_id.reset(token_b)

        token = current_tenant_id.set("tenant-a")
        try:
            result = await tenant_session.execute(select(_TenantItem))
            items = result.scalars().all()
            assert len(items) == 2
            assert all(i.tenant_id == "tenant-a" for i in items)
        finally:
            current_tenant_id.reset(token)

        token = current_tenant_id.set("tenant-b")
        try:
            result = await tenant_session.execute(select(_TenantItem))
            items = result.scalars().all()
            assert len(items) == 1
            assert items[0].name == "B1"
        finally:
            current_tenant_id.reset(token)

    async def test_no_filtering_without_tenant_context(self, tenant_session: AsyncSession):
        """Without a tenant context, all rows should be visible (system query)."""
        token_a = current_tenant_id.set("tenant-a")
        try:
            tenant_session.add(_TenantItem(name="A1"))
            await tenant_session.flush()
        finally:
            current_tenant_id.reset(token_a)

        token_b = current_tenant_id.set("tenant-b")
        try:
            tenant_session.add(_TenantItem(name="B1"))
            await tenant_session.flush()
        finally:
            current_tenant_id.reset(token_b)

        result = await tenant_session.execute(select(_TenantItem))
        items = result.scalars().all()
        assert len(items) == 2

    async def test_cross_tenant_creation_rejected(self, tenant_session: AsyncSession):
        """Creating an object with a tenant_id that doesn't match the context should raise."""
        token = current_tenant_id.set("tenant-a")
        try:
            item = _TenantItem(name="Imposter", tenant_id="tenant-b")
            tenant_session.add(item)
            with pytest.raises(TenantIsolationError, match="Cannot create object"):
                await tenant_session.flush()
        finally:
            await tenant_session.rollback()
            current_tenant_id.reset(token)

    async def test_tenant_id_change_rejected(self, tenant_session: AsyncSession):
        """Changing tenant_id on an existing object should raise."""
        token = current_tenant_id.set("tenant-a")
        try:
            item = _TenantItem(name="Stable")
            tenant_session.add(item)
            await tenant_session.flush()

            item.tenant_id = "tenant-b"
            with pytest.raises(TenantIsolationError, match="Cannot change tenant_id"):
                await tenant_session.flush()
        finally:
            await tenant_session.rollback()
            current_tenant_id.reset(token)


class TestMultiTenancyEdgeCases:
    """Edge cases: updates, session.get, filter composition, and error recovery."""

    async def test_update_within_same_tenant(self, tenant_session: AsyncSession):
        """Updating a non-tenant field on a same-tenant object should succeed."""
        token = current_tenant_id.set("tenant-a")
        try:
            item = _TenantItem(name="Original")
            tenant_session.add(item)
            await tenant_session.flush()

            item.name = "Renamed"
            await tenant_session.flush()

            assert item.name == "Renamed"
            assert item.tenant_id == "tenant-a"
        finally:
            current_tenant_id.reset(token)

    async def test_reassigning_same_tenant_id_is_allowed(self, tenant_session: AsyncSession):
        """Setting tenant_id to its current value is a no-op, not a violation."""
        token = current_tenant_id.set("tenant-a")
        try:
            item = _TenantItem(name="A")
            tenant_session.add(item)
            await tenant_session.flush()

            item.tenant_id = "tenant-a"
            await tenant_session.flush()

            assert item.tenant_id == "tenant-a"
        finally:
            current_tenant_id.reset(token)

    async def test_session_get_respects_tenant_filter(self, tenant_session: AsyncSession):
        """session.get() for an item owned by another tenant should return None."""
        token_a = current_tenant_id.set("tenant-a")
        try:
            item = _TenantItem(name="Belongs to A")
            tenant_session.add(item)
            await tenant_session.flush()
            tenant_a_item_id = item.id
            tenant_session.expunge(item)
        finally:
            current_tenant_id.reset(token_a)

        token_b = current_tenant_id.set("tenant-b")
        try:
            found = await tenant_session.get(_TenantItem, tenant_a_item_id)
            assert found is None
        finally:
            current_tenant_id.reset(token_b)

        token_a = current_tenant_id.set("tenant-a")
        try:
            found = await tenant_session.get(_TenantItem, tenant_a_item_id)
            assert found is not None
            assert found.tenant_id == "tenant-a"
        finally:
            current_tenant_id.reset(token_a)

    async def test_tenant_filter_composes_with_soft_delete_filter(
        self, tenant_session: AsyncSession
    ):
        """A model using both mixins should be filtered by tenant AND is_deleted=False."""
        token_a = current_tenant_id.set("tenant-a")
        try:
            alive = _TenantSoftItem(name="alive-a")
            deleted = _TenantSoftItem(name="deleted-a")
            tenant_session.add_all([alive, deleted])
            await tenant_session.flush()

            await tenant_session.delete(deleted)
            await tenant_session.flush()
        finally:
            current_tenant_id.reset(token_a)

        token_b = current_tenant_id.set("tenant-b")
        try:
            tenant_session.add(_TenantSoftItem(name="alive-b"))
            await tenant_session.flush()
        finally:
            current_tenant_id.reset(token_b)

        token = current_tenant_id.set("tenant-a")
        try:
            result = await tenant_session.execute(select(_TenantSoftItem))
            rows = result.scalars().all()
            assert len(rows) == 1
            assert rows[0].name == "alive-a"
            assert rows[0].is_deleted is False
        finally:
            current_tenant_id.reset(token)

    async def test_cross_tenant_violation_does_not_leak_state(self, tenant_session: AsyncSession):
        """After a raised TenantIsolationError and rollback, the session is usable."""
        token = current_tenant_id.set("tenant-a")
        try:
            bad = _TenantItem(name="bad", tenant_id="tenant-b")
            tenant_session.add(bad)
            with pytest.raises(TenantIsolationError):
                await tenant_session.flush()

            await tenant_session.rollback()

            good = _TenantItem(name="good")
            tenant_session.add(good)
            await tenant_session.flush()
            assert good.tenant_id == "tenant-a"
        finally:
            current_tenant_id.reset(token)

    async def test_creation_without_tenant_or_context_fails_at_db(
        self, tenant_session: AsyncSession
    ):
        """No tenant context and no explicit tenant_id → NOT NULL constraint fires."""
        item = _TenantItem(name="Orphan")
        tenant_session.add(item)
        with pytest.raises(IntegrityError):
            await tenant_session.flush()
        await tenant_session.rollback()

    async def test_system_operation_sees_all_tenants(self, tenant_session: AsyncSession):
        """Without a tenant context, a system query can read across all tenants."""
        for tenant in ("tenant-a", "tenant-b", "tenant-c"):
            token = current_tenant_id.set(tenant)
            try:
                tenant_session.add(_TenantItem(name=f"item-{tenant}"))
                await tenant_session.flush()
            finally:
                current_tenant_id.reset(token)

        result = await tenant_session.execute(select(_TenantItem))
        rows = result.scalars().all()
        tenants = {r.tenant_id for r in rows}
        assert tenants == {"tenant-a", "tenant-b", "tenant-c"}

    async def test_tenant_context_scoped_to_async_task(self, tenant_session: AsyncSession):
        """ContextVar changes in one task don't leak into a concurrent task."""
        seen: list[str | None] = []

        async def read_tenant() -> None:
            seen.append(current_tenant_id.get())

        token = current_tenant_id.set("tenant-a")
        try:
            await asyncio.create_task(read_tenant())
        finally:
            current_tenant_id.reset(token)

        assert current_tenant_id.get() is None
        assert seen == ["tenant-a"]
