"""Tests for the users.UserAccessToken SQLAlchemy model."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import inspect, select


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
