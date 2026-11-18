"""Real SQLite queries keep eligibility filtering ahead of the result limit."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from users.core.directory import UsersDirectory
from users.models import User


@pytest.fixture
def directory_db():
    engine = create_engine("sqlite://")
    User.__table__.create(engine)
    with engine.connect() as connection:
        yield SimpleNamespace(execute=AsyncMock(side_effect=connection.execute)), connection
    engine.dispose()


def insert_user(connection, email, **kwargs):
    uid = uuid.uuid4()
    connection.execute(User.__table__.insert().values(id=uid, email=email, **kwargs))
    return str(uid)


async def test_eligible_member_after_200_foreign_matches(directory_db):
    db, connection = directory_db
    for n in range(200):
        insert_user(connection, f"alex{n:03}@example.com")
    friend = insert_user(connection, "z-alex@example.com")
    found = await UsersDirectory().search(db, "alex", limit=1, include_ids=[friend])
    assert [u.id for u in found] == [friend]
    assert await UsersDirectory().search(db, "alex", limit=1, include_ids=[]) == []


async def test_activity_and_exclusions_precede_limit(directory_db):
    db, connection = directory_db
    for n in range(200):
        insert_user(connection, f"alex{n:03}@example.com", is_active=False)
    insert_user(connection, "alex-disabled@example.com", disabled_at=datetime.now(UTC))
    owner = insert_user(connection, "alex-owner@example.com")
    caller = insert_user(connection, "alex-caller@example.com")
    friend = insert_user(connection, "z-alex@example.com")
    found = await UsersDirectory().search(
        db, "alex", limit=1, active_only=True, exclude_ids=[owner, caller]
    )
    assert [u.id for u in found] == [friend]
    # Existing callers still receive inactive users unless they opt in.
    unfiltered = await UsersDirectory().search(db, "alex000", limit=1)
    assert not unfiltered[0].is_active


async def test_exact_email_is_case_insensitive_and_literal(directory_db):
    db, connection = directory_db
    insert_user(connection, "alex_x@example.com")
    insert_user(connection, "alexYx@example.com", full_name="alex_x@example.com")
    directory = UsersDirectory()
    found = await directory.search(db, "ALEX_X@EXAMPLE.COM", limit=10, exact_email=True)
    assert [u.email for u in found] == ["alex_x@example.com"]
    assert await directory.search(db, "alex", limit=10, exact_email=True) == []
