"""Tests for the database layer: base creation, mixins, session, deps."""

from __future__ import annotations

from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin, SoftDeleteMixin, VersionedMixin
from simple_module_db.provider import DatabaseProvider, detect_provider
from simple_module_db.session import DatabaseState, init_db
from sqlalchemy.ext.asyncio import AsyncSession

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


# ── DB logging ──────────────────────────────────────────────────────


class TestGetDbLogging:
    async def test_commit_logs_session_commit(self, caplog):
        """get_db should log db.session.commit on successful exit."""
        import contextlib
        import logging
        from unittest.mock import MagicMock

        from simple_module_db.deps import get_db

        db_state = init_db("sqlite+aiosqlite:///:memory:")
        try:
            mock_request = MagicMock()
            mock_request.app.state.db = db_state

            with caplog.at_level(logging.INFO, logger="simple_module.db"):
                gen = get_db(mock_request)
                await gen.__anext__()
                with contextlib.suppress(StopAsyncIteration):
                    await gen.__anext__()

            db_messages = [r for r in caplog.records if r.name == "simple_module.db"]
            commit_msgs = [r for r in db_messages if r.message == "db.session.commit"]
            assert len(commit_msgs) == 1
            assert commit_msgs[0].operation == "commit"  # type: ignore[attr-defined]
            assert hasattr(commit_msgs[0], "db_duration_ms")
        finally:
            await db_state.engine.dispose()


class TestEntityListenerLogging:
    async def test_create_logs_entity_created(self, db_session: AsyncSession, caplog):
        """Inserting a new entity should log db.entity.created."""
        import logging

        from sm_products.models import Product

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

        from sm_products.models import Product

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
