"""Which registrations get the standard ``user`` role (GH #488 review).

OAuth provisioning is not gated by ``allow_signup``, so the role it attaches
must be: with signups closed, an account any provider user can create holds no
role until an admin grants one.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from users.constants import OAUTH_REGISTRATION_REQUEST_FLAG
from users.manager import UserManager
from users.models import UserRole
from users.settings import UsersSettings

_ROLE_ID = uuid.uuid4()


def _manager(*, allow_signup: bool) -> UserManager:
    settings = UsersSettings(
        verification_token_secret="test-verify-secret-at-least-32-bytes-long",
        reset_password_token_secret="test-reset-secret-at-least-32-bytes-long",
        allow_signup=allow_signup,
    )
    user_db = MagicMock()
    user_db.update = AsyncMock()
    user_db.session.flush = AsyncMock()
    user_db.session.commit = AsyncMock()
    user_db.session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=MagicMock(id=_ROLE_ID)))
    )
    return UserManager(user_db, MagicMock(send_verification=AsyncMock()), settings)


def _request(*, oauth: bool) -> MagicMock:
    request = MagicMock()
    request.app.state.sm.event_bus = MagicMock(publish=AsyncMock())
    request.state = SimpleNamespace(**({OAUTH_REGISTRATION_REQUEST_FLAG: True} if oauth else {}))
    return request


def _user() -> MagicMock:
    return MagicMock(id=uuid.uuid4(), email="new@example.com", is_verified=True)


def _added_roles(manager: UserManager) -> list[UserRole]:
    return [
        c.args[0]
        for c in manager.user_db.session.add.call_args_list
        if isinstance(c.args[0], UserRole)
    ]


@pytest.mark.anyio
async def test_oauth_provisioning_with_signup_closed_gets_no_role():
    manager = _manager(allow_signup=False)
    await manager.on_after_register(_user(), _request(oauth=True))
    assert _added_roles(manager) == []


@pytest.mark.anyio
async def test_oauth_provisioning_with_signup_open_gets_the_user_role():
    manager = _manager(allow_signup=True)
    user = _user()
    await manager.on_after_register(user, _request(oauth=True))
    (link,) = _added_roles(manager)
    assert (link.user_id, link.role_id) == (user.id, _ROLE_ID)


@pytest.mark.anyio
async def test_local_registration_gets_the_user_role():
    # /register itself 404s while signup is closed, so reaching the hook
    # means the operator opened it.
    manager = _manager(allow_signup=True)
    user = _user()
    await manager.on_after_register(user, _request(oauth=False))
    (link,) = _added_roles(manager)
    assert (link.user_id, link.role_id) == (user.id, _ROLE_ID)
