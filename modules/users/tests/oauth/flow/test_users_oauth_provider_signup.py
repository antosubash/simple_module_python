"""Listed providers provision accounts with local signup closed (#874)."""

from __future__ import annotations

import pytest
from _users_microsoft_support import install_microsoft
from _users_oauth_support import (
    find_user,
    install_fake_provider,
    oauth_callback,
    set_users_settings,
)


@pytest.mark.anyio
async def test_listed_provider_with_proven_email_creates_the_account(users_app, anon_client):
    set_users_settings(users_app, allow_signup=False, oauth_signup_providers=["oidc"])
    install_fake_provider(users_app, "staff-1", "staff@example.com")

    assert (await oauth_callback(anon_client)).status_code == 303
    user = await find_user(users_app, "staff@example.com")
    assert user is not None and user.is_external and user.is_verified


@pytest.mark.anyio
@pytest.mark.parametrize("allow_signup", [False, True])
async def test_listed_provider_without_email_proof_is_refused(users_app, anon_client, allow_signup):
    """Listing a provider never widens it: an unproven email creates nothing."""
    set_users_settings(users_app, allow_signup=allow_signup, oauth_signup_providers=["microsoft"])
    install_microsoft(users_app, trust=False, preferred_username="who@example.com")

    resp = await oauth_callback(anon_client, "microsoft")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "OAUTH_SIGNUP_DISABLED"
    assert await find_user(users_app, "who@example.com") is None


@pytest.mark.anyio
async def test_unlisted_provider_still_follows_allow_signup(users_app, anon_client):
    set_users_settings(users_app, allow_signup=False, oauth_signup_providers=["microsoft"])
    install_fake_provider(users_app, "oidc-1", "other@example.com")

    resp = await oauth_callback(anon_client)
    assert resp.json()["detail"] == "OAUTH_SIGNUP_DISABLED"


@pytest.mark.anyio
async def test_local_registration_stays_closed(users_app, anon_client):
    set_users_settings(users_app, allow_signup=False, oauth_signup_providers=["oidc"])

    page = await anon_client.get("/users/register")
    api = await anon_client.post(
        "/api/users/auth/register",
        json={"email": "local@example.com", "password": "SecurePass1!"},
    )
    assert page.status_code == 404
    assert api.status_code == 404
    assert await find_user(users_app, "local@example.com") is None
