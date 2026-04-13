"""Tests for the database layer: base creation, mixins, session, deps."""

from __future__ import annotations

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


class _TenantItem(_TenantBase, MultiTenantMixin):  # type: ignore[misc]
    __tablename__ = "mt_test_item"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))

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

    @pytest.fixture
    async def tenant_session(self) -> AsyncSession:
        """Session backed by in-memory SQLite with tenant listeners registered."""
        db_state = init_db("sqlite+aiosqlite:///:memory:")
        register_listeners(db_state)

        async with db_state.engine.begin() as conn:
            await conn.run_sync(_TenantBase.metadata.create_all)

        async with db_state.session_factory() as session:
            yield session  # type: ignore[misc]

        await db_state.engine.dispose()

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
