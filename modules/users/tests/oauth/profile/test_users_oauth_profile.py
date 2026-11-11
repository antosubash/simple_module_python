"""OAuth sign-ins store the IdP profile on the link (#877)."""

from __future__ import annotations

import pytest
from _users_microsoft_support import OID, TENANT, install_microsoft
from _users_oauth_support import (
    find_user,
    oauth_callback,
    seed_password_user,
    set_allow_signup,
    set_users_settings,
)
from sqlalchemy import select
from users.models import OAuthAccount

_EMAIL = "jane@corp.com"


async def _link(app) -> OAuthAccount:
    async with app.state.sm.db.session_factory() as session:
        return (await session.execute(select(OAuthAccount))).scalar_one()


@pytest.mark.anyio
async def test_a_new_account_gets_the_profile_and_the_name(users_app, anon_client):
    set_allow_signup(users_app, True)
    install_microsoft(users_app, name="Jane Doe")

    assert (await oauth_callback(anon_client, "microsoft")).status_code == 303
    link = await _link(users_app)
    assert (link.subject, link.username, link.display_name) == ("pairwise-sub", _EMAIL, "Jane Doe")
    assert link.extra == {"oid": OID, "tid": TENANT}
    assert link.last_sign_in_at is not None
    assert (await find_user(users_app, _EMAIL)).full_name == "Jane Doe"


@pytest.mark.anyio
@pytest.mark.parametrize("sync, expected", [(False, "Jane Doe"), (True, "Jane Smith")])
async def test_later_sign_ins_sync_the_name_only_when_asked(users_app, anon_client, sync, expected):
    set_allow_signup(users_app, True)
    install_microsoft(users_app, name="Jane Doe")
    assert (await oauth_callback(anon_client, "microsoft")).status_code == 303
    first = (await _link(users_app)).last_sign_in_at
    anon_client.cookies.clear()

    set_users_settings(users_app, oauth_sync_profile=sync)
    install_microsoft(users_app, name="Jane Smith")
    assert (await oauth_callback(anon_client, "microsoft")).status_code == 303

    link = await _link(users_app)
    assert link.display_name == "Jane Smith"
    assert link.last_sign_in_at >= first
    assert (await find_user(users_app, _EMAIL)).full_name == expected


@pytest.mark.anyio
async def test_linking_an_existing_account_keeps_its_name(users_app, anon_client):
    await seed_password_user(users_app, _EMAIL, is_verified=True, full_name="J. Doe")
    install_microsoft(users_app, name="Jane Doe")

    assert (await oauth_callback(anon_client, "microsoft")).status_code == 303
    assert (await _link(users_app)).display_name == "Jane Doe"
    assert (await find_user(users_app, _EMAIL)).full_name == "J. Doe"
