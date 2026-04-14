"""Tests for the database layer: base creation, mixins, session, deps."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from simple_module_db.base import create_module_base
from simple_module_db.listeners import TenantIsolationError, current_tenant_id, register_listeners
from simple_module_db.mixins import AuditMixin, MultiTenantMixin, SoftDeleteMixin, VersionedMixin
from simple_module_db.provider import DatabaseProvider, detect_provider
from simple_module_db.session import DatabaseState, init_db
from sqlalchemy import String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

# ── Test model for multi-tenancy ────────────────────────────────────
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


# ── create_module_base ───────────────────────────────────────────────


class TestCreateModuleBase:
    async def test_returns_declarative_base(self):
        base = create_module_base("test_mod_base", provider=DatabaseProvider.SQLITE)
        # It should be a class that can be used as a SQLAlchemy base
        assert hasattr(base, "metadata")
        assert base.__abstract__ is True  # ty: ignore[unresolved-attribute]

    async def test_caching_same_args(self):
        base1 = create_module_base("cache_test", provider=DatabaseProvider.SQLITE)
        base2 = create_module_base("cache_test", provider=DatabaseProvider.SQLITE)
        assert base1 is base2

    async def test_different_providers_different_bases(self):
        base_sqlite = create_module_base("multi_prov", provider=DatabaseProvider.SQLITE)
        base_pg = create_module_base("multi_prov", provider=DatabaseProvider.POSTGRESQL)
        assert base_sqlite is not base_pg

    async def test_postgresql_uses_schema(self):
        base = create_module_base("schemamod", provider=DatabaseProvider.POSTGRESQL)
        assert base.metadata.schema == "schemamod"

    async def test_sqlite_no_schema(self):
        base = create_module_base("noschemod", provider=DatabaseProvider.SQLITE)
        assert base.metadata.schema is None

    async def test_module_name_stored(self):
        base = create_module_base("named_mod", provider=DatabaseProvider.SQLITE)
        assert base.__module_name__ == "named_mod"  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

    async def test_all_module_bases_is_deduped(self):
        """Re-creating the same module must not grow ``all_module_bases``."""
        from simple_module_db import base as base_mod

        # Prime both caches, then snapshot.
        create_module_base("dedupe_test", provider=DatabaseProvider.SQLITE)
        before = len(base_mod.all_module_bases)

        # Second call returns cached base; list length must not change.
        create_module_base("dedupe_test", provider=DatabaseProvider.SQLITE)
        after = len(base_mod.all_module_bases)

        assert after == before
        assert create_module_base("dedupe_test", provider=DatabaseProvider.SQLITE) in (
            base_mod.all_module_bases
        )


# ── detect_provider ──────────────────────────────────────────────────


class TestDetectProvider:
    async def test_sqlite(self):
        assert detect_provider("sqlite+aiosqlite:///:memory:") == DatabaseProvider.SQLITE

    async def test_postgresql(self):
        assert (
            detect_provider("postgresql+asyncpg://user:pass@localhost/db")
            == DatabaseProvider.POSTGRESQL
        )

    async def test_postgres_prefix(self):
        assert detect_provider("postgres://user:pass@localhost/db") == DatabaseProvider.POSTGRESQL


# ── Mixins ───────────────────────────────────────────────────────────


class TestMixins:
    async def test_audit_mixin_fields(self):
        """AuditMixin should define created_at, updated_at, created_by, updated_by."""
        fields = ["created_at", "updated_at", "created_by", "updated_by"]
        for field_name in fields:
            assert hasattr(AuditMixin, field_name), f"AuditMixin missing {field_name}"

    async def test_soft_delete_mixin_fields(self):
        """SoftDeleteMixin should define is_deleted, deleted_at, deleted_by."""
        fields = ["is_deleted", "deleted_at", "deleted_by"]
        for field_name in fields:
            assert hasattr(SoftDeleteMixin, field_name), f"SoftDeleteMixin missing {field_name}"

    async def test_versioned_mixin_fields(self):
        assert hasattr(VersionedMixin, "version")


# ── init_db / DatabaseState ──────────────────────────────────────────


class TestSessionManagement:
    async def test_init_db_returns_database_state(self):
        """init_db should return a DatabaseState with engine and session factory."""
        db_state = init_db("sqlite+aiosqlite:///:memory:")
        try:
            assert isinstance(db_state, DatabaseState)
            assert db_state.engine is not None
            assert db_state.session_factory is not None
        finally:
            await db_state.engine.dispose()

    async def test_separate_init_db_calls_are_independent(self):
        """Two init_db calls should produce independent state."""
        db1 = init_db("sqlite+aiosqlite:///:memory:")
        db2 = init_db("sqlite+aiosqlite:///:memory:")
        try:
            assert db1.engine is not db2.engine
            assert db1.session_factory is not db2.session_factory
        finally:
            await db1.engine.dispose()
            await db2.engine.dispose()


# ── get_db dependency ────────────────────────────────────────────────


class TestGetDbDependency:
    async def test_get_db_yields_session(self):
        """get_db should yield an AsyncSession from app.state.db."""
        import contextlib
        from unittest.mock import MagicMock

        from simple_module_db.deps import get_db

        db_state = init_db("sqlite+aiosqlite:///:memory:")
        try:
            mock_request = MagicMock()
            mock_request.app.state.db = db_state

            gen = get_db(mock_request)
            session = await gen.__anext__()
            assert isinstance(session, AsyncSession)

            with contextlib.suppress(StopAsyncIteration):
                await gen.__anext__()
        finally:
            await db_state.engine.dispose()


# ── Multi-tenancy ───────────────────────────────────────────────────


class TestMultiTenancy:
    """Automatic tenant isolation: auto-populate, query filtering, enforcement."""

    # ── auto-populate ───────────────────────────────────────

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

    # ── query filtering ─────────────────────────────────────

    async def test_query_returns_only_current_tenant(self, tenant_session: AsyncSession):
        """SELECT should be automatically filtered to the current tenant."""
        # Seed two tenants
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

        # Query as tenant-a
        token = current_tenant_id.set("tenant-a")
        try:
            result = await tenant_session.execute(select(_TenantItem))
            items = result.scalars().all()
            assert len(items) == 2
            assert all(i.tenant_id == "tenant-a" for i in items)
        finally:
            current_tenant_id.reset(token)

        # Query as tenant-b
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

        # No tenant context → see everything
        result = await tenant_session.execute(select(_TenantItem))
        items = result.scalars().all()
        assert len(items) == 2

    # ── isolation enforcement ───────────────────────────────

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

            # Attempt to move to another tenant
            item.tenant_id = "tenant-b"
            with pytest.raises(TenantIsolationError, match="Cannot change tenant_id"):
                await tenant_session.flush()
        finally:
            await tenant_session.rollback()
            current_tenant_id.reset(token)

    async def test_multi_tenant_mixin_fields(self):
        """MultiTenantMixin should define tenant_id."""
        assert hasattr(MultiTenantMixin, "tenant_id")


# ── Multi-tenancy edge cases ────────────────────────────────────────


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
        # Seed an item for tenant-a
        token_a = current_tenant_id.set("tenant-a")
        try:
            item = _TenantItem(name="Belongs to A")
            tenant_session.add(item)
            await tenant_session.flush()
            tenant_a_item_id = item.id
            tenant_session.expunge(item)  # Drop from identity map so get() hits DB
        finally:
            current_tenant_id.reset(token_a)

        # Try to fetch from tenant-b — filter should hide it
        token_b = current_tenant_id.set("tenant-b")
        try:
            found = await tenant_session.get(_TenantItem, tenant_a_item_id)
            assert found is None
        finally:
            current_tenant_id.reset(token_b)

        # Same id, correct tenant → visible
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
        # Seed: two items for tenant-a, one alive and one soft-deleted; one item for tenant-b.
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

        # tenant-a should only see the alive item (soft-deleted one filtered out)
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

            # Session should be usable again
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
        from sqlalchemy.exc import IntegrityError

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
        import asyncio

        seen: list[str | None] = []

        async def read_tenant() -> None:
            # New task inherits the ContextVar snapshot at task creation time
            seen.append(current_tenant_id.get())

        token = current_tenant_id.set("tenant-a")
        try:
            await asyncio.create_task(read_tenant())
        finally:
            current_tenant_id.reset(token)

        assert current_tenant_id.get() is None
        # The task saw the value that was current when it was created
        assert seen == ["tenant-a"]


# ── DB logging ──────────────────────────────────────────────────────


class TestGetDbLogging:
    """The ``db_state`` fixture handles engine setup/teardown; these tests
    just need to create tables and drive ``get_db`` against a mock request.
    """

    @staticmethod
    async def _drive_get_db(db_state, populate=None):
        """Yield the session, let ``populate`` touch it, then let the
        dependency close — this mirrors FastAPI's request lifecycle.
        """
        import contextlib
        from unittest.mock import MagicMock

        from simple_module_db.deps import get_db

        mock_request = MagicMock()
        mock_request.app.state.db = db_state
        gen = get_db(mock_request)
        session = await gen.__anext__()
        if populate is not None:
            await populate(session)
        with contextlib.suppress(StopAsyncIteration):
            await gen.__anext__()

    async def test_commit_logs_on_write(self, db_state, caplog):
        import logging

        async with db_state.engine.begin() as conn:
            await conn.run_sync(_TenantBase.metadata.create_all)

        async def add_one(session):
            session.add(_TenantItem(name="w", tenant_id="t1"))

        with caplog.at_level(logging.INFO, logger="simple_module.db"):
            await self._drive_get_db(db_state, populate=add_one)

        commits = [
            r
            for r in caplog.records
            if r.name == "simple_module.db" and r.message == "db.session.commit"
        ]
        assert len(commits) == 1
        assert commits[0].operation == "commit"  # type: ignore[attr-defined]
        assert hasattr(commits[0], "db_duration_ms")

    async def test_commit_fires_even_after_explicit_flush(self, db_state, caplog):
        """After flush clears ``session.new`` the ``has_writes`` tag from
        the after_flush listener must still drive the commit path. This
        guards the real-world pattern used by service.create().
        """
        import logging

        async with db_state.engine.begin() as conn:
            await conn.run_sync(_TenantBase.metadata.create_all)

        async def add_and_flush(session):
            session.add(_TenantItem(name="w", tenant_id="t1"))
            await session.flush()
            assert not session.new  # flush emptied the live collection

        with caplog.at_level(logging.INFO, logger="simple_module.db"):
            await self._drive_get_db(db_state, populate=add_and_flush)

        commits = [
            r
            for r in caplog.records
            if r.name == "simple_module.db" and r.message == "db.session.commit"
        ]
        assert len(commits) == 1

    async def test_read_only_skips_commit(self, db_state, caplog):
        import logging

        with caplog.at_level(logging.DEBUG, logger="simple_module.db"):
            await self._drive_get_db(db_state)

        records = [r for r in caplog.records if r.name == "simple_module.db"]
        assert [r for r in records if r.message == "db.session.commit"] == []
        read_only = [r for r in records if r.message == "db.session.read_only"]
        assert len(read_only) == 1
        assert read_only[0].operation == "read_only_rollback"  # type: ignore[attr-defined]


class TestEntityListenerLogging:
    async def test_create_logs_entity_created(self, db_session: AsyncSession, caplog):
        """Inserting a new entity should log db.entity.created."""
        import logging

        from products.models import Product

        with caplog.at_level(logging.INFO, logger="simple_module.db"):
            product = Product(name="Widget", price=9.99)
            db_session.add(product)
            await db_session.flush()

        created_msgs = [
            r
            for r in caplog.records
            if r.name == "simple_module.db" and r.message == "db.entity.created"
        ]
        assert len(created_msgs) == 1
        assert created_msgs[0].entity == "Product"  # type: ignore[attr-defined]
        assert created_msgs[0].operation == "create"  # type: ignore[attr-defined]

    async def test_update_logs_entity_updated(self, db_session: AsyncSession, caplog):
        """Modifying an entity should log db.entity.updated."""
        import logging

        from products.models import Product

        product = Product(name="Widget", price=9.99)
        db_session.add(product)
        await db_session.flush()

        caplog.clear()

        product.name = "Updated Widget"
        with caplog.at_level(logging.INFO, logger="simple_module.db"):
            await db_session.flush()

        updated_msgs = [
            r
            for r in caplog.records
            if r.name == "simple_module.db" and r.message == "db.entity.updated"
        ]
        assert len(updated_msgs) == 1
        assert updated_msgs[0].entity == "Product"  # type: ignore[attr-defined]
        assert updated_msgs[0].operation == "update"  # type: ignore[attr-defined]
        assert updated_msgs[0].entity_id is not None  # type: ignore[attr-defined]
