"""Tests for the database layer: base creation, mixins, session, deps."""

from __future__ import annotations

import pytest
from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin, SoftDeleteMixin, VersionedMixin
from simple_module_db.provider import DatabaseProvider, detect_provider
from simple_module_db.session import get_engine, get_session_factory, init_db
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

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


# ── init_db / get_engine / get_session_factory ───────────────────────


class TestSessionManagement:
    async def test_init_db_and_get_engine(self):
        """init_db should configure the engine and session factory."""
        import simple_module_db.session as session_mod

        # Save original state
        orig_engine = session_mod._engine
        orig_factory = session_mod._session_factory

        try:
            session_mod._engine = None
            session_mod._session_factory = None

            init_db("sqlite+aiosqlite:///:memory:")
            engine = get_engine()
            assert engine is not None

            factory = get_session_factory()
            assert factory is not None
        finally:
            # Restore to avoid polluting other tests
            if session_mod._engine and session_mod._engine is not orig_engine:
                await session_mod._engine.dispose()
            session_mod._engine = orig_engine
            session_mod._session_factory = orig_factory

    async def test_get_engine_raises_without_init(self):
        import simple_module_db.session as session_mod

        orig_engine = session_mod._engine
        try:
            session_mod._engine = None
            with pytest.raises(RuntimeError, match="Database not initialized"):
                get_engine()
        finally:
            session_mod._engine = orig_engine

    async def test_get_session_factory_raises_without_init(self):
        import simple_module_db.session as session_mod

        orig_factory = session_mod._session_factory
        try:
            session_mod._session_factory = None
            with pytest.raises(RuntimeError, match="Database not initialized"):
                get_session_factory()
        finally:
            session_mod._session_factory = orig_factory


# ── get_db dependency ────────────────────────────────────────────────


class TestGetDbDependency:
    async def test_get_db_yields_session(self, engine: AsyncEngine):
        """get_db should yield an AsyncSession when init_db has been called."""
        import simple_module_db.session as session_mod

        orig_engine = session_mod._engine
        orig_factory = session_mod._session_factory

        try:
            session_mod._engine = engine
            session_mod._session_factory = async_sessionmaker(engine, expire_on_commit=False)

            from simple_module_db.deps import get_db

            gen = get_db()
            session = await gen.__anext__()
            assert isinstance(session, AsyncSession)
            # Clean up
            import contextlib

            with contextlib.suppress(StopAsyncIteration):
                await gen.__anext__()
        finally:
            session_mod._engine = orig_engine
            session_mod._session_factory = orig_factory
