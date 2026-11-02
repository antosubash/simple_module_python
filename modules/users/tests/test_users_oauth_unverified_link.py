"""OAuth never links by email to an unverified password account (GH #547).

With ``require_verification`` off anyone can register ``victim@corp.com`` with
a password and sign in. If the real owner later signs in with SSO, associating
by email would hand them — and the attacker — one shared account.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from _users_oauth_support import (
    install_fake_provider,
    oauth_callback,
    seed_password_user,
    set_allow_signup,
)
from fastapi_users.password import PasswordHelper
from sqlalchemy import select
from users.models import OAuthAccount, User

_EMAIL = "victim@example.com"


async def _links(app, user_id: uuid.UUID) -> list[OAuthAccount]:
    async with app.state.sm.db.session_factory() as session:
        stmt = select(OAuthAccount).where(OAuthAccount.user_id == user_id)
        return list((await session.execute(stmt)).scalars())


@pytest.mark.anyio
@pytest.mark.parametrize("allow_signup", [True, False])
async def test_unverified_password_account_is_not_linked(users_app, anon_client, allow_signup):
    set_allow_signup(users_app, allow_signup)
    user_id = await seed_password_user(users_app, _EMAIL, is_verified=False)
    install_fake_provider(users_app, "ms-victim", _EMAIL)

    resp = await oauth_callback(anon_client)

    assert resp.status_code == 403
    assert resp.json()["detail"] == "OAUTH_ACCOUNT_NOT_VERIFIED"
    assert users_app.state.users.settings.cookie_name not in resp.cookies
    assert await _links(users_app, user_id) == []


@pytest.mark.anyio
async def test_verified_account_links(users_app, anon_client):
    user_id = await seed_password_user(users_app, _EMAIL, is_verified=True)
    install_fake_provider(users_app, "ms-owner", _EMAIL)

    assert (await oauth_callback(anon_client)).status_code == 303
    assert [a.account_id for a in await _links(users_app, user_id)] == ["ms-owner"]


@pytest.mark.anyio
async def test_pending_invite_links(users_app, anon_client):
    """An invite's password is random and unknown, so nobody else holds the account."""
    user_id = await seed_password_user(
        users_app, _EMAIL, is_verified=False, invited_at=datetime.now(UTC)
    )
    install_fake_provider(users_app, "ms-invitee", _EMAIL)

    assert (await oauth_callback(anon_client)).status_code == 303
    assert len(await _links(users_app, user_id)) == 1


@pytest.mark.anyio
async def test_already_linked_account_signs_in(users_app, anon_client):
    """Found by its OAuth link, not by email — verification is not asked for."""
    set_allow_signup(users_app, True)
    install_fake_provider(users_app, "ms-linked", "linked@example.com")
    assert (await oauth_callback(anon_client)).status_code == 303
    async with users_app.state.sm.db.session_factory() as session:
        user = (
            await session.execute(select(User).where(User.email == "linked@example.com"))
        ).scalar_one()
        user.is_verified = False
        user.hashed_password = PasswordHelper().hash("SecurePass1!")
        user.is_external = False
        await session.commit()

    anon_client.cookies.clear()
    assert (await oauth_callback(anon_client)).status_code == 303
