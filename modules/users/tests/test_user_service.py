"""Tests for UserService domain-level error behavior."""

from __future__ import annotations

import uuid

import pytest


def _build_service(session, users_app):
    """Build a UserService directly (bypass FastAPI Depends)."""
    from users.db_adapter import UserDatabaseWithRoles
    from users.manager import UserManager
    from users.models import User
    from users.service import UserService

    user_db = UserDatabaseWithRoles(session, User)
    manager = UserManager(
        user_db,
        users_app.state.users.mailer,
        users_app.state.users.settings,
    )
    return UserService(session, manager)


@pytest.mark.anyio
async def test_disable_unknown_user_raises_user_not_found(users_app):
    from users.exceptions import UserNotFoundError

    async with users_app.state.sm.db.session_factory() as session:
        service = _build_service(session, users_app)
        with pytest.raises(UserNotFoundError):
            await service.disable(uuid.uuid4())


@pytest.mark.anyio
async def test_enable_unknown_user_raises_user_not_found(users_app):
    from users.exceptions import UserNotFoundError

    async with users_app.state.sm.db.session_factory() as session:
        service = _build_service(session, users_app)
        with pytest.raises(UserNotFoundError):
            await service.enable(uuid.uuid4())


@pytest.mark.anyio
async def test_set_roles_unknown_user_raises_user_not_found(users_app):
    from users.exceptions import UserNotFoundError

    async with users_app.state.sm.db.session_factory() as session:
        service = _build_service(session, users_app)
        with pytest.raises(UserNotFoundError):
            await service.set_roles(uuid.uuid4(), ["user"])


@pytest.mark.anyio
async def test_generate_reset_link_unknown_user_raises_user_not_found(users_app):
    from users.exceptions import UserNotFoundError

    async with users_app.state.sm.db.session_factory() as session:
        service = _build_service(session, users_app)
        with pytest.raises(UserNotFoundError):
            await service.generate_reset_link(uuid.uuid4(), "http://testserver")


@pytest.mark.anyio
async def test_get_list_item_unknown_user_raises_user_not_found(users_app):
    from users.exceptions import UserNotFoundError

    async with users_app.state.sm.db.session_factory() as session:
        service = _build_service(session, users_app)
        with pytest.raises(UserNotFoundError):
            await service.get_list_item(uuid.uuid4())


@pytest.mark.anyio
async def test_to_list_item_includes_created_at(users_app):
    """`UserListItem` carries `created_at` sourced from AuditMixin."""
    from fastapi_users.password import PasswordHelper
    from users.db_adapter import UserDatabaseWithRoles
    from users.manager import UserManager
    from users.models import User
    from users.service import UserService

    async with users_app.state.sm.db.session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            email="ts@example.com",
            hashed_password=PasswordHelper().hash("x"),
            is_active=True,
            is_superuser=False,
            is_verified=True,
        )
        session.add(user)
        await session.flush()

        user_db = UserDatabaseWithRoles(session, User)
        manager = UserManager(
            user_db,
            users_app.state.users.mailer,
            users_app.state.users.settings,
        )
        svc = UserService(session, manager)
        item = await svc.get_list_item(user.id)
        assert item.created_at is not None
