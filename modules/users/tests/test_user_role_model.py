"""Tests for the users.UserRole SQLAlchemy model.

Includes structure tests, CRUD integration tests, and seed-migration invariants.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import selectinload


class TestUserRoleTableShape:
    def test_tablename(self):
        from users.models import UserRole

        assert UserRole.__tablename__ == "users_user_role"

    def test_composite_pk_columns(self):
        from users.models import UserRole

        mapper = inspect(UserRole)
        pk_cols = {col.key for col in mapper.primary_key}
        assert pk_cols == {"user_id", "role_id"}


@pytest.mark.anyio
async def test_user_role_composite_pk(db_session):
    """Insert a User + Role + UserRole, then retrieve via the association."""
    from users.models import Role, User, UserRole

    user_id = uuid.uuid4()
    role_id = uuid.uuid4()

    user = User(
        id=user_id,
        email="crud@example.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    role = Role(id=role_id, name="testrole")
    link = UserRole(user_id=user_id, role_id=role_id)

    db_session.add_all([user, role, link])
    await db_session.commit()

    result = await db_session.execute(
        select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.role_id == role_id,
        )
    )
    row = result.scalar_one()
    assert row.user_id == user_id
    assert row.role_id == role_id


@pytest.mark.anyio
async def test_fk_cascade_delete_user_removes_user_role(db_session):
    """Deleting a User cascades and removes associated UserRole rows."""
    from users.models import Role, User, UserRole

    user_id = uuid.uuid4()
    role_id = uuid.uuid4()

    user = User(
        id=user_id,
        email="cascade@example.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    role = Role(id=role_id, name="cascade_role")
    link = UserRole(user_id=user_id, role_id=role_id)

    db_session.add_all([user, role, link])
    await db_session.commit()

    # Enable FK enforcement for SQLite (it's off by default)
    await db_session.execute(text("PRAGMA foreign_keys=ON"))

    await db_session.delete(user)
    await db_session.commit()

    result = await db_session.execute(select(UserRole).where(UserRole.user_id == user_id))
    assert result.scalar_one_or_none() is None


@pytest.mark.anyio
async def test_seed_inserted_role_joins_orm_user_role(db_session):
    """Role rows inserted the way the seed migration does them must JOIN with
    ORM-inserted UserRole links.

    Regression: the seed migration used ``sa.Uuid()`` which on SQLite stores
    UUIDs as 32-char hex without dashes, while the schema column (``GUID`` from
    fastapi_users_db_sqlalchemy) keeps dashes — so ORM-linked UserRole rows
    failed to JOIN the seeded Role rows and admins silently lost their role.
    """
    from users.models import User, UserRole

    role_id = uuid.UUID("00000000-0000-0000-0000-0000000000aa")

    # Mirror the seed migration: raw insert via sa.table(...) with GUID column.
    roles_table = sa.table(
        "users_role",
        sa.column("id", GUID()),
        sa.column("name", sa.String()),
    )
    await db_session.execute(sa.insert(roles_table).values(id=role_id, name="seed_admin"))

    user = User(
        id=uuid.uuid4(),
        email="seed@example.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id=role_id))
    await db_session.commit()

    loaded = (
        await db_session.execute(
            select(User).where(User.id == user.id).options(selectinload(User.roles))
        )
    ).scalar_one()
    assert [r.name for r in loaded.roles] == ["seed_admin"]
