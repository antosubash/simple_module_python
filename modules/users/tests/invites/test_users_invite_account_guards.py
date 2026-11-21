"""Invite tokens cannot revive disabled or external accounts (#1071)."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi_users import exceptions
from fastapi_users.jwt import generate_jwt
from users.contracts.schemas import AcceptInviteRequest
from users.invites.accept import complete_invite
from users.invites.preview import preview_invite


def _invite(**changes):
    user = SimpleNamespace(
        id=uuid4(),
        email="invite@example.com",
        is_active=True,
        disabled_at=None,
        is_external=False,
        is_verified=False,
        roles=[],
    )
    for name, value in changes.items():
        setattr(user, name, value)
    manager = SimpleNamespace(
        verification_token_secret="test-secret-at-least-thirty-two-characters",
        verification_token_audience="verify",
        get_by_email=AsyncMock(return_value=user),
        parse_id=lambda value: type(user.id)(value),
        validate_password=AsyncMock(),
        user_db=SimpleNamespace(update=AsyncMock(return_value=user)),
        password_helper=SimpleNamespace(hash=MagicMock(return_value="new-hash")),
        on_after_verify=AsyncMock(),
        on_after_update=AsyncMock(),
    )
    token = generate_jwt(
        {"sub": str(user.id), "email": user.email, "aud": "verify"},
        "test-secret-at-least-thirty-two-characters",
        3600,
    )
    return user, manager, token


@pytest.mark.parametrize(
    "changes",
    [
        {"is_active": False},
        {"disabled_at": datetime(2026, 1, 1, tzinfo=UTC)},
        {"is_external": True},
    ],
)
async def test_accept_rejects_ineligible_account_before_writing(changes):
    _, manager, token = _invite(**changes)
    with pytest.raises(exceptions.InvalidVerifyToken):
        await complete_invite(
            manager, AcceptInviteRequest(token=token, password="SecurePassword1!"), None
        )
    manager.validate_password.assert_not_called()
    manager.user_db.update.assert_not_called()


@pytest.mark.parametrize(
    "changes",
    [
        {"is_active": False},
        {"disabled_at": datetime(2026, 1, 1, tzinfo=UTC)},
        {"is_external": True},
        {"is_verified": True},
        {"id": uuid4()},
    ],
)
async def test_preview_hides_ineligible_or_replaced_account(changes):
    user, manager, token = _invite()
    for name, value in changes.items():
        setattr(user, name, value)
    assert await preview_invite(token, manager) is None


async def test_preview_hides_missing_account():
    _, manager, token = _invite()
    manager.get_by_email.side_effect = exceptions.UserNotExists()
    assert await preview_invite(token, manager) is None
