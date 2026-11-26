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


async def test_name_only_search_filters_before_limit(directory_db):
    db, connection = directory_db
    directory = UsersDirectory()
    email_match = insert_user(connection, "alex@example.com")
    insert_user(connection, "empty@example.com", full_name="")
    named = insert_user(connection, "z@example.com", full_name="Alex Smith")
    assert [u.id for u in await directory.search(db, "alex", limit=1)] == [email_match]
    found = await directory.search(db, " ALEX ", limit=1, match_email=False)
    assert [u.id for u in found] == [named]
    assert await directory.search(db, "alex", limit=1, match_email=False, include_ids=[]) == []
    assert await directory.search(db, "alex", limit=1, match_email=False, exclude_ids=[named]) == []
    assert len(await directory.search(db, " ", limit=10, match_email=False)) == 3


@pytest.mark.parametrize("term", ["%", "_", "\\"])
async def test_name_only_search_matches_literal_metacharacters(directory_db, term):
    db, connection = directory_db
    insert_user(connection, f"a{term}@example.com", full_name="Ada")
    named = insert_user(connection, "z@example.com", full_name=f"Ada{term}Lovelace")
    found = await UsersDirectory().search(db, term, limit=1, match_email=False)
    assert [u.id for u in found] == [named]


async def test_find_by_email_is_exact_case_insensitive_and_literal(directory_db):
    db, connection = directory_db
    directory = UsersDirectory()
    named = insert_user(
        connection, "Ada_X@Example.com", full_name="Ada", disabled_at=datetime.now(UTC)
    )
    insert_user(connection, "adaYx@example.com", full_name="Ada_X@Example.com")
    found = await directory.find_by_email(db, " ADA_X@EXAMPLE.COM ")
    assert found is not None and found.id == named
    assert found.full_name == "Ada"
    assert not found.is_active
    for email in ["ada", "%@example.com", "missing@example.com", "", " "]:
        assert await directory.find_by_email(db, email) is None
    found = await directory.search(
        db, "ada_x@example.com", limit=1, match_email=False, exact_email=True
    )
    assert [u.id for u in found] == [named]


async def test_large_member_filter_chunks_queries_and_keeps_global_limit(directory_db):
    db, connection = directory_db
    ids = [uuid.UUID(int=n + 1) for n in range(32768)]
    for index, email in [(0, "z@test"), (500, "b@test"), (1000, "c@test"), (-1, "a@test")]:
        connection.execute(User.__table__.insert().values(id=ids[index], email=email))
    found = await UsersDirectory().search(db, None, limit=3, include_ids=[str(uid) for uid in ids])
    assert [user.email for user in found] == ["a@test", "b@test", "c@test"]
    statements = [call.args[0] for call in db.execute.call_args_list]
    assert len(statements) > 1
    assert all(
        len(stmt.compile(compile_kwargs={"render_postcompile": True}).params) <= 505
        for stmt in statements
    )
