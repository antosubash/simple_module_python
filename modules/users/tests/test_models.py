"""Tests for the users module SQLAlchemy models.

Uses the root conftest's ``db_session`` fixture which runs ``create_all``
against an in-memory SQLite database, so the tables exist but the seed
migration data (admin/user roles) is not present — we insert what we need
inside each test.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import inspect, select, text

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def column_names(table) -> set[str]:
    """Return the set of column names for a mapped class's table."""
    return {c.key for c in inspect(table).mapper.column_attrs}


# ---------------------------------------------------------------------------
# Model structure tests
# ---------------------------------------------------------------------------


class TestUserTableShape:
    def test_tablename(self):
        from users.models import User

        assert User.__tablename__ == "users_user"

    def test_required_columns(self):
        from users.models import User

        cols = column_names(User)
        expected = {
            "id",
            "email",
            "hashed_password",
            "is_active",
            "is_superuser",
            "is_verified",
            "full_name",
            "tenant_id",
            "disabled_at",
            "last_login_at",
            # AuditMixin columns
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        }
        assert expected <= cols, f"Missing columns: {expected - cols}"


class TestRoleTableShape:
    def test_tablename(self):
        from users.models import Role

        assert Role.__tablename__ == "users_role"

    def test_required_columns(self):
        from users.models import Role

        cols = column_names(Role)
        expected = {
            "id",
            "name",
            "description",
            # AuditMixin columns
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        }
        assert expected <= cols, f"Missing columns: {expected - cols}"


class TestUserRoleTableShape:
    def test_tablename(self):
        from users.models import UserRole

        assert UserRole.__tablename__ == "users_user_role"

    def test_composite_pk_columns(self):
        from users.models import UserRole

        mapper = inspect(UserRole)
        pk_cols = {col.key for col in mapper.primary_key}
        assert pk_cols == {"user_id", "role_id"}


class TestUserAccessTokenTableShape:
    def test_tablename(self):
        from users.models import UserAccessToken

        assert UserAccessToken.__tablename__ == "users_access_token"

    def test_user_id_fk_points_at_users_user(self):
        from users.models import UserAccessToken

        table = inspect(UserAccessToken).persist_selectable
        fk_targets = {
            next(iter(col.foreign_keys)).target_fullname
            for col in table.columns
            if col.foreign_keys
        }
        assert "users_user.id" in fk_targets


# ---------------------------------------------------------------------------
# CRUD / integration tests (using db_session)
# ---------------------------------------------------------------------------


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
async def test_user_access_token_insert(db_session):
    """UserAccessToken can be created with a valid user_id FK."""
    from users.models import User, UserAccessToken

    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email="token@example.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()

    token = UserAccessToken(token="a" * 43, user_id=user_id)
    db_session.add(token)
    await db_session.commit()

    result = await db_session.execute(
        select(UserAccessToken).where(UserAccessToken.token == "a" * 43)
    )
    row = result.scalar_one()
    assert row.user_id == user_id


# ---------------------------------------------------------------------------
# Seed-migration <-> ORM storage-format invariant
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_seed_inserted_role_joins_orm_user_role(db_session):
    """Role rows inserted the way the seed migration does them must JOIN with
    ORM-inserted UserRole links.

    Regression: the seed migration used ``sa.Uuid()`` which on SQLite stores
    UUIDs as 32-char hex without dashes, while the schema column (``GUID`` from
    fastapi_users_db_sqlalchemy) keeps dashes — so ORM-linked UserRole rows
    failed to JOIN the seeded Role rows and admins silently lost their role.
    """
    import sqlalchemy as sa
    from fastapi_users_db_sqlalchemy.generics import GUID
    from sqlalchemy.orm import selectinload
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


# ---------------------------------------------------------------------------
# Stable UUID constants tests
# ---------------------------------------------------------------------------


class TestConstants:
    def test_admin_role_id_is_stable(self):
        from users.constants import ADMIN_ROLE_ID

        assert str(ADMIN_ROLE_ID) == "00000000-0000-0000-0000-000000000001"

    def test_user_role_id_is_stable(self):
        from users.constants import USER_ROLE_ID

        assert str(USER_ROLE_ID) == "00000000-0000-0000-0000-000000000002"

    def test_admin_uuid_hex(self):
        from users.constants import ADMIN_ROLE_ID

        assert ADMIN_ROLE_ID.hex == "00000000000000000000000000000001"

    def test_user_uuid_hex(self):
        from users.constants import USER_ROLE_ID

        assert USER_ROLE_ID.hex == "00000000000000000000000000000002"

    def test_ids_differ(self):
        from users.constants import ADMIN_ROLE_ID, USER_ROLE_ID

        assert ADMIN_ROLE_ID != USER_ROLE_ID
