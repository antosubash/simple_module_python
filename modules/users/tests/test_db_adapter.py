"""Tests for UserDatabaseWithRoles."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from users.constants import ADMIN_ROLE_ID, USER_ROLE_ID


@pytest.fixture
async def _seed_roles(db_session):
    """Insert admin and user roles into the test DB."""
    from users.models import Role

    existing = (await db_session.execute(select(Role.name))).scalars().all()
    if "admin" not in existing:
        db_session.add(Role(id=ADMIN_ROLE_ID, name="admin", description="Administrator"))
    if "user" not in existing:
        db_session.add(Role(id=USER_ROLE_ID, name="user", description="Standard user"))
    await db_session.commit()


@pytest.fixture
async def test_user(db_session, _seed_roles):
    """Insert a user with the 'admin' role and return it."""
    from users.models import User, UserRole

    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email="adapter-test@example.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    link = UserRole(user_id=user_id, role_id=ADMIN_ROLE_ID)
    db_session.add(link)
    await db_session.commit()

    # Expire all objects so subsequent fetches hit the DB
    db_session.expire_all()
    return user_id, "adapter-test@example.com"


@pytest.mark.anyio
async def test_get_by_email_returns_user_with_roles(db_session, test_user):
    from users.db_adapter import UserDatabaseWithRoles
    from users.models import User

    user_id, email = test_user
    db = UserDatabaseWithRoles(db_session, User)

    user = await db.get_by_email(email)

    assert user is not None
    assert user.id == user_id
    # roles must be populated (no implicit lazy load would raise in async)
    assert len(user.roles) == 1
    assert user.roles[0].name == "admin"


@pytest.mark.anyio
async def test_get_returns_user_with_roles(db_session, test_user):
    from users.db_adapter import UserDatabaseWithRoles
    from users.models import User

    user_id, _ = test_user
    db = UserDatabaseWithRoles(db_session, User)

    user = await db.get(user_id)

    assert user is not None
    assert user.id == user_id
    assert len(user.roles) == 1
    assert user.roles[0].name == "admin"


@pytest.mark.anyio
async def test_get_by_email_case_insensitive(db_session, test_user):
    """get_by_email uses func.lower so lookup is case-insensitive."""
    from users.db_adapter import UserDatabaseWithRoles
    from users.models import User

    _, email = test_user
    db = UserDatabaseWithRoles(db_session, User)

    user = await db.get_by_email(email.upper())
    assert user is not None


@pytest.mark.anyio
async def test_get_nonexistent_returns_none(db_session):
    from users.db_adapter import UserDatabaseWithRoles
    from users.models import User

    db = UserDatabaseWithRoles(db_session, User)
    result = await db.get(uuid.uuid4())
    assert result is None


@pytest.mark.anyio
async def test_get_by_email_nonexistent_returns_none(db_session):
    from users.db_adapter import UserDatabaseWithRoles
    from users.models import User

    db = UserDatabaseWithRoles(db_session, User)
    result = await db.get_by_email("nobody@example.com")
    assert result is None


@pytest.mark.anyio
async def test_user_with_no_roles_returns_empty_list(db_session):
    from users.db_adapter import UserDatabaseWithRoles
    from users.models import User

    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email="noroles@example.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    db_session.expire_all()

    db = UserDatabaseWithRoles(db_session, User)
    fetched = await db.get(user_id)

    assert fetched is not None
    assert fetched.roles == []
