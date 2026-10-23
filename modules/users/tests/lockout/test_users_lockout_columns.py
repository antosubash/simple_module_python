"""Login-lockout columns on ``users_user`` (GH #530)."""

from __future__ import annotations

from datetime import UTC, datetime

from simple_module_db.audit import snapshot_changes
from sqlalchemy import select
from users.models import User


async def _admin(users_db) -> User:
    return (await users_db.execute(select(User).limit(1))).scalar_one()


async def test_existing_user_starts_unlocked(users_db) -> None:
    user = await _admin(users_db)
    assert user.failed_login_count == 0
    assert user.last_failed_login_at is None
    assert user.locked_until is None


async def test_counter_fields_are_not_audited(users_db) -> None:
    user = await _admin(users_db)
    user.failed_login_count = 3
    user.last_failed_login_at = datetime.now(UTC)
    assert snapshot_changes(users_db.sync_session) == []

    user.locked_until = datetime.now(UTC)
    [record] = snapshot_changes(users_db.sync_session)
    assert [c["field"] for c in record.changes] == ["locked_until"]
