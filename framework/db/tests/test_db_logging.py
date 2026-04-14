"""Tests for session- and entity-level database logging."""

from __future__ import annotations

import contextlib
import logging
from unittest.mock import MagicMock

from simple_module_db.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from conftest import _TenantBase, _TenantItem  # noqa: E402  # ty: ignore[unresolved-import]


async def _drive_get_db(db_state, populate=None):
    """Yield the session, let ``populate`` touch it, then let the dependency
    close — this mirrors FastAPI's request lifecycle.
    """
    mock_request = MagicMock()
    mock_request.app.state.db = db_state
    gen = get_db(mock_request)
    session = await gen.__anext__()
    if populate is not None:
        await populate(session)
    with contextlib.suppress(StopAsyncIteration):
        await gen.__anext__()


class TestGetDbLogging:
    """The ``db_state`` fixture handles engine setup/teardown; these tests
    just need to create tables and drive ``get_db`` against a mock request.
    """

    async def test_commit_logs_on_write(self, db_state, caplog):
        async with db_state.engine.begin() as conn:
            await conn.run_sync(_TenantBase.metadata.create_all)

        async def add_one(session):
            session.add(_TenantItem(name="w", tenant_id="t1"))

        with caplog.at_level(logging.INFO, logger="simple_module.db"):
            await _drive_get_db(db_state, populate=add_one)

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
        async with db_state.engine.begin() as conn:
            await conn.run_sync(_TenantBase.metadata.create_all)

        async def add_and_flush(session):
            session.add(_TenantItem(name="w", tenant_id="t1"))
            await session.flush()
            assert not session.new

        with caplog.at_level(logging.INFO, logger="simple_module.db"):
            await _drive_get_db(db_state, populate=add_and_flush)

        commits = [
            r
            for r in caplog.records
            if r.name == "simple_module.db" and r.message == "db.session.commit"
        ]
        assert len(commits) == 1

    async def test_read_only_skips_commit(self, db_state, caplog):
        with caplog.at_level(logging.DEBUG, logger="simple_module.db"):
            await _drive_get_db(db_state)

        records = [r for r in caplog.records if r.name == "simple_module.db"]
        assert [r for r in records if r.message == "db.session.commit"] == []
        read_only = [r for r in records if r.message == "db.session.read_only"]
        assert len(read_only) == 1
        assert read_only[0].operation == "read_only_rollback"  # type: ignore[attr-defined]


class TestEntityListenerLogging:
    async def test_create_logs_entity_created(self, db_session: AsyncSession, caplog):
        """Inserting a new entity should log db.entity.created."""
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
