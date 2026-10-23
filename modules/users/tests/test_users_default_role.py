"""Which registrations receive the standard role, using real checkpoint sessions."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import select
from users.constants import OAUTH_REGISTRATION_REQUEST_FLAG, USER_ROLE_ID
from users.db_adapter import UserDatabaseWithRoles
from users.manager import UserManager
from users.models import OAuthAccount, Role, User, UserRole


def _manager(app, session, *, allow_signup: bool) -> UserManager:
    settings = app.state.users.settings.model_copy(update={"allow_signup": allow_signup})
    return UserManager(
        UserDatabaseWithRoles(session, User, OAuthAccount),
        MagicMock(send_verification=AsyncMock()),
        settings,
    )


def _request(*, oauth: bool) -> MagicMock:
    request = MagicMock()
    request.app.state.sm.event_bus = MagicMock(publish=AsyncMock())
    request.state = SimpleNamespace(**({OAUTH_REGISTRATION_REQUEST_FLAG: True} if oauth else {}))
    return request


async def _user(session) -> User:
    user = User(email="new@example.com", is_verified=True)
    session.add(user)
    await session.commit()  # fastapi-users creates the account before invoking its hook
    return user


async def _roles(session, user: User) -> list:
    return list(
        (
            await session.execute(select(UserRole.role_id).where(UserRole.user_id == user.id))
        ).scalars()
    )


async def test_oauth_provisioning_with_signup_closed_gets_no_role(users_app, users_db):
    manager = _manager(users_app, users_db, allow_signup=False)
    user = await _user(users_db)
    await manager.on_after_register(user, _request(oauth=True))
    assert await _roles(users_db, user) == []


async def test_oauth_provisioning_with_signup_open_gets_the_user_role(users_app, users_db):
    manager = _manager(users_app, users_db, allow_signup=True)
    user = await _user(users_db)
    await manager.on_after_register(user, _request(oauth=True))
    assert await _roles(users_db, user) == [USER_ROLE_ID]


async def test_request_bound_registration_gets_the_user_role(users_app, users_db):
    manager = _manager(users_app, users_db, allow_signup=True)
    user = await _user(users_db)
    await manager.on_after_register(user, _request(oauth=False))
    assert await _roles(users_db, user) == [USER_ROLE_ID]


async def test_a_deleted_user_role_is_not_recreated(users_app, users_db):
    role = await users_db.get(Role, USER_ROLE_ID)
    await users_db.delete(role)
    await users_db.commit()
    manager = _manager(users_app, users_db, allow_signup=True)
    user = await _user(users_db)
    await manager.on_after_register(user, _request(oauth=False))
    assert await _roles(users_db, user) == []
    assert await users_db.get(Role, USER_ROLE_ID) is None
