"""Microsoft sign-in for pre-approved staff with signup closed (#873).

With ``oauth_microsoft_trust_tenant_upn`` effective, a member UPN is proof of
the email, so it links to an invited or verified local account. The guards for
unproven accounts and guests stay.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from _users_oauth_support import (
    install_fake_provider,
    oauth_callback,
    seed_password_user,
    set_allow_signup,
)
from sqlalchemy import select
from users.models import OAuthAccount

_EMAIL = "jane@corp.com"


def _microsoft(app, upn: str = _EMAIL, *, trust: bool = True) -> None:
    install_fake_provider(app, "ms-jane", upn, provider="microsoft", trust_email=trust)


@pytest.mark.anyio
async def test_invited_account_signs_in_with_signup_closed(users_app, anon_client):
    set_allow_signup(users_app, False)
    user_id = await seed_password_user(
        users_app, _EMAIL, is_verified=False, invited_at=datetime.now(UTC)
    )
    _microsoft(users_app)

    assert (await oauth_callback(anon_client, "microsoft")).status_code == 303
    async with users_app.state.sm.db.session_factory() as session:
        links = (await session.execute(select(OAuthAccount.user_id))).scalars().all()
    assert links == [user_id]


@pytest.mark.anyio
async def test_verified_account_links_instead_of_already_exists(users_app, anon_client):
    set_allow_signup(users_app, False)
    await seed_password_user(users_app, _EMAIL, is_verified=True)
    _microsoft(users_app)

    assert (await oauth_callback(anon_client, "microsoft")).status_code == 303


@pytest.mark.anyio
async def test_without_trust_a_verified_account_is_still_refused(users_app, anon_client):
    set_allow_signup(users_app, False)
    await seed_password_user(users_app, _EMAIL, is_verified=True)
    _microsoft(users_app, trust=False)

    resp = await oauth_callback(anon_client, "microsoft")
    assert resp.json()["detail"] == "OAUTH_USER_ALREADY_EXISTS"


@pytest.mark.anyio
async def test_unproven_local_account_is_still_refused(users_app, anon_client):
    await seed_password_user(users_app, _EMAIL, is_verified=False)
    _microsoft(users_app)

    resp = await oauth_callback(anon_client, "microsoft")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "OAUTH_ACCOUNT_NOT_VERIFIED"


@pytest.mark.anyio
async def test_guest_upn_does_not_link(users_app, anon_client):
    guest = "jane_corp.com#EXT#@other.onmicrosoft.com"
    await seed_password_user(users_app, guest, is_verified=True)
    _microsoft(users_app, guest)

    resp = await oauth_callback(anon_client, "microsoft")
    assert resp.json()["detail"] == "OAUTH_USER_ALREADY_EXISTS"


@pytest.mark.anyio
async def test_signup_gate_still_applies_to_unknown_staff(users_app, anon_client):
    set_allow_signup(users_app, False)
    _microsoft(users_app)

    resp = await oauth_callback(anon_client, "microsoft")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "OAUTH_SIGNUP_DISABLED"
