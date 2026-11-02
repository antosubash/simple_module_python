"""The database lock behind the first-admin wizard action, across connections.

``test_users_setup_wizard`` drives concurrency through one app, where the
in-process lock already serializes requests (and an in-memory SQLite engine
shares one connection anyway). Two workers share neither, so the database lock
is the real guarantee — exercised here on two real connections.
"""

from __future__ import annotations

import os

import pytest
import sqlalchemy as sa
from simple_module_db import init_db
from sqlalchemy.exc import OperationalError
from users.models import User
from users.setup_action import _lock_admin_creation

pytestmark = pytest.mark.anyio


async def test_sqlite_lock_holds_off_a_second_writer(tmp_path) -> None:
    state = init_db(f"sqlite+aiosqlite:///{tmp_path / 'lock.db'}", sqlite_busy_timeout_ms=100)
    try:
        async with state.engine.begin() as conn:
            await conn.run_sync(lambda sync: User.__table__.create(sync))

        async with state.session_factory() as first, state.session_factory() as second:
            await _lock_admin_creation(first)

            with pytest.raises(OperationalError, match="locked"):
                await _lock_admin_creation(second)
            await second.rollback()

            # Released at commit: the next worker gets through and re-checks.
            await first.commit()
            await _lock_admin_creation(second)
            await second.rollback()
    finally:
        await state.engine.dispose()


@pytest.mark.skipif(
    not os.environ.get("SM_TEST_DATABASE_URL", "").startswith("postgresql"),
    reason="needs SM_TEST_DATABASE_URL pointing at Postgres",
)
async def test_postgres_advisory_lock_is_held_for_the_transaction() -> None:
    state = init_db(os.environ["SM_TEST_DATABASE_URL"])
    try:
        async with state.session_factory() as first, state.session_factory() as second:
            await _lock_admin_creation(first)
            probe = sa.text("SELECT pg_try_advisory_xact_lock(:key)")
            from users.setup_action import _PG_LOCK_KEY

            assert await second.scalar(probe, {"key": _PG_LOCK_KEY}) is False
            await second.rollback()

            await first.commit()
            assert await second.scalar(probe, {"key": _PG_LOCK_KEY}) is True
            await second.rollback()
    finally:
        await state.engine.dispose()
