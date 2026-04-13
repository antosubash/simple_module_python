"""Tests for the database layer: base creation, mixins, session, deps."""

from __future__ import annotations

import pytest
from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin, SoftDeleteMixin, VersionedMixin
from simple_module_db.provider import DatabaseProvider, detect_provider
from simple_module_db.session import DatabaseState, init_db
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
    async def test_get_db_yields_session(self, engine: AsyncEngine):
        """get_db should yield an AsyncSession from app.state.db."""
        from unittest.mock import MagicMock

        from simple_module_db.deps import get_db
        from simple_module_db.session import DatabaseState

        db_state = DatabaseState(
            engine=engine,
            session_factory=async_sessionmaker(engine, expire_on_commit=False),
        )

        # Mock a FastAPI request with app.state.db
        mock_request = MagicMock()
        mock_request.app.state.db = db_state

        gen = get_db(mock_request)
        session = await gen.__anext__()
        assert isinstance(session, AsyncSession)
        import contextlib

        with contextlib.suppress(StopAsyncIteration):
            await gen.__anext__()
