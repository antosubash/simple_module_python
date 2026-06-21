"""UserService write-op tests: create / update / delete."""

from __future__ import annotations

import uuid

import pytest
from test_service_admin import _build_service

# ---------------------------------------------------------------------------
# create_user
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_create_user_active_verified_with_roles(users_app):
    """create_user makes an active+verified user and assigns roles."""
    async with users_app.state.sm.db.session_factory() as session:
        svc = _build_service(session, users_app)
        user = await svc.create_user(
            email="created@example.com",
            password="SecurePass1!",
            full_name="Created User",
            role_names=["user"],
            created_by="admin-id",
        )
        assert user.is_active is True
        assert user.is_verified is True
        assert user.email == "created@example.com"
        assert user.full_name == "Created User"
        assert [r.name for r in user.roles] == ["user"]


@pytest.mark.anyio
async def test_create_user_weak_password_rejected(users_app):
    from fastapi_users import exceptions as fa_exc

    async with users_app.state.sm.db.session_factory() as session:
        svc = _build_service(session, users_app)
        with pytest.raises(fa_exc.InvalidPasswordException):
            await svc.create_user(
                email="weak@example.com",
                password="short",
                full_name=None,
                role_names=[],
                created_by=None,
            )


@pytest.mark.anyio
async def test_create_user_duplicate_email_rejected(users_app):
    from fastapi_users import exceptions as fa_exc

    async with users_app.state.sm.db.session_factory() as session:
        svc = _build_service(session, users_app)
        await svc.create_user(
            email="dup@example.com",
            password="SecurePass1!",
            full_name=None,
            role_names=[],
            created_by=None,
        )
        await session.flush()
        with pytest.raises(fa_exc.UserAlreadyExists):
            await svc.create_user(
                email="dup@example.com",
                password="SecurePass1!",
                full_name=None,
                role_names=[],
                created_by=None,
            )


# ---------------------------------------------------------------------------
# update_details
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_update_details_changes_email_and_name(users_app):
    from test_api_admin import _make_user

    async with users_app.state.sm.db.session_factory() as session:
        user = await _make_user(session, email="old@example.com")
        svc = _build_service(session, users_app)
        updated = await svc.update_details(user.id, email="new@example.com", full_name="New Name")
        assert updated.email == "new@example.com"
        assert updated.full_name == "New Name"


@pytest.mark.anyio
async def test_update_details_duplicate_email_rejected(users_app):
    from test_api_admin import _make_user
    from users.exceptions import EmailAlreadyExistsError

    async with users_app.state.sm.db.session_factory() as session:
        await _make_user(session, email="a@example.com")
        target = await _make_user(session, email="b@example.com")
        svc = _build_service(session, users_app)
        with pytest.raises(EmailAlreadyExistsError):
            await svc.update_details(target.id, email="a@example.com", full_name=None)


@pytest.mark.anyio
async def test_update_details_same_email_is_allowed(users_app):
    from test_api_admin import _make_user

    async with users_app.state.sm.db.session_factory() as session:
        user = await _make_user(session, email="keep@example.com")
        svc = _build_service(session, users_app)
        updated = await svc.update_details(user.id, email="keep@example.com", full_name="Renamed")
        assert updated.email == "keep@example.com"
        assert updated.full_name == "Renamed"


# ---------------------------------------------------------------------------
# delete_user
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_delete_user_removes_user_and_all_child_rows(users_app):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select
    from test_api_admin import _make_user
    from users.models import (
        OAuthAccount,
        RefreshToken,
        User,
        UserAccessToken,
        UserRole,
    )

    async with users_app.state.sm.db.session_factory() as session:
        user = await _make_user(session, email="todelete@example.com", role_names=["admin"])
        session.add(UserAccessToken(token=f"tok-{user.id.hex}", user_id=user.id))
        session.add(
            OAuthAccount(
                user_id=user.id,
                oauth_name="google",
                access_token="x",
                account_id="acct-1",
                account_email="todelete@example.com",
            )
        )
        session.add(
            RefreshToken(user_id=user.id, expires_at=datetime.now(UTC) + timedelta(days=1))
        )
        await session.flush()

        svc = _build_service(session, users_app)
        await svc.delete_user(user.id)

        assert (
            await session.execute(select(User).where(User.id == user.id))
        ).scalar_one_or_none() is None
        for model in (UserRole, UserAccessToken, OAuthAccount, RefreshToken):
            rows = (
                (await session.execute(select(model).where(model.user_id == user.id)))
                .scalars()
                .all()
            )
            assert rows == [], f"{model.__name__} rows not cleaned up"


@pytest.mark.anyio
async def test_delete_user_nonexistent_raises(users_app):
    from users.exceptions import UserNotFoundError

    async with users_app.state.sm.db.session_factory() as session:
        svc = _build_service(session, users_app)
        with pytest.raises(UserNotFoundError):
            await svc.delete_user(uuid.uuid4())
