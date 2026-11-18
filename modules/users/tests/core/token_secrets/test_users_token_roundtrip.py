"""Exercise real manager signing and validation without a database driver."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi_users import exceptions
from users.accounts.manager import UserManager
from users.core.password_hashing import PASSWORD_HELPER
from users.core.settings import UsersSettings
from users.core.token_secrets import resolve_token_secrets
from users.models import User


@pytest.mark.parametrize("legacy", [False, True])
async def test_manager_tokens_survive_reconstruction(monkeypatch, legacy):
    monkeypatch.delenv("SM_USERS_RESET_PASSWORD_TOKEN_SECRET", raising=False)
    monkeypatch.delenv("SM_USERS_VERIFICATION_TOKEN_SECRET", raising=False)
    if legacy:
        monkeypatch.setenv(
            "SM_USERS_RESET_PASSWORD_TOKEN_SECRET", "legacy-reset-key-32-bytes-long-xxx"
        )
        monkeypatch.setenv(
            "SM_USERS_VERIFICATION_TOKEN_SECRET", "legacy-verify-key-32-bytes-long-xx"
        )
    user = User(
        id=uuid.uuid4(),
        email="owner@example.com",
        hashed_password=PASSWORD_HELPER.hash("OriginalPassword1!"),
        is_verified=False,
    )

    async def update(user, values):
        for name, value in values.items():
            setattr(user, name, value)
        return user

    db = SimpleNamespace(
        get=AsyncMock(return_value=user),
        get_by_email=AsyncMock(return_value=user),
        update=update,
        session=object(),
    )
    # Only credential-row revocation needs SQL; JWT and password validation stay real.
    monkeypatch.setattr("users.accounts.reset_revocation.revoke_credential_rows", AsyncMock())
    first = UserManager(db, None, UsersSettings(), resolve_token_secrets("stable-root"))
    reset_token = await first.generate_reset_password_token(user)
    verify_token = first.mint_invite_token(user)
    second = UserManager(
        db,
        None,
        UsersSettings(),
        resolve_token_secrets("another-root" if legacy else "stable-root"),
    )
    assert (await second.verify(verify_token)).is_verified is True
    changed = await second.reset_password(reset_token, "ReplacementPassword1!")
    assert PASSWORD_HELPER.verify_and_update("ReplacementPassword1!", changed.hashed_password)[0]
    with pytest.raises(exceptions.InvalidResetPasswordToken):
        await second.reset_password(reset_token, "AnotherPassword1!")


async def test_root_rotation_rejects_outstanding_derived_links(monkeypatch):
    monkeypatch.delenv("SM_USERS_RESET_PASSWORD_TOKEN_SECRET", raising=False)
    monkeypatch.delenv("SM_USERS_VERIFICATION_TOKEN_SECRET", raising=False)
    user = User(id=uuid.uuid4(), email="owner@example.com", hashed_password="unused")
    first = UserManager(None, None, UsersSettings(), resolve_token_secrets("old-root"))
    rotated = UserManager(None, None, UsersSettings(), resolve_token_secrets("new-root"))
    with pytest.raises(exceptions.InvalidVerifyToken):
        await rotated.verify(first.mint_invite_token(user))
    with pytest.raises(exceptions.InvalidResetPasswordToken):
        await rotated.reset_password(await first.generate_reset_password_token(user), "NewPass1!")
