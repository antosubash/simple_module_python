"""Only a proven provider email may link an existing account (GH #622)."""

from urllib.parse import parse_qs, urlparse

import pytest
from _users_oauth_support import find_user, seed_password_user, set_allow_signup
from sqlalchemy import select
from users.models import OAuthAccount
from users.oauth import OAuthProvider

_EMAIL = "victim@example.com"


class _ClaimClient:
    def __init__(self, claim):
        self.profile = {"sub": "idp-attacker", "email": _EMAIL, **claim}

    async def get_authorization_url(self, redirect_uri, state):
        return f"https://idp.example/authorize?state={state}"

    async def get_access_token(self, code, redirect_uri):
        return {"access_token": "fake-token"}

    async def get_profile(self, token):
        return self.profile

    async def get_id_email(self, token):
        return self.profile["sub"], self.profile["email"]


async def _callback(app, client, claim, provider="oidc"):
    app.state.users.oauth_clients[provider] = OAuthProvider(provider, provider, _ClaimClient(claim))
    login = await client.get(f"/api/users/auth/{provider}/login")
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    return await client.get(f"/api/users/auth/{provider}/callback?code=abc&state={state}")


@pytest.mark.anyio
@pytest.mark.parametrize("allow_signup", [False, True])
@pytest.mark.parametrize("claim", [{}, {"email_verified": False}, {"email_verified": "true"}])
async def test_oidc_unproven_email_cannot_link_verified_user(
    users_app, anon_client, claim, allow_signup
):
    set_allow_signup(users_app, allow_signup)
    user_id = await seed_password_user(users_app, _EMAIL, is_verified=True)

    response = await _callback(users_app, anon_client, claim)

    assert response.status_code == 400
    assert response.json()["detail"] == "OAUTH_USER_ALREADY_EXISTS"
    assert users_app.state.users.settings.cookie_name not in response.cookies
    async with users_app.state.sm.db.session_factory() as session:
        assert list((await session.execute(select(OAuthAccount))).scalars()) == []
    assert (await find_user(users_app, _EMAIL)).id == user_id


@pytest.mark.anyio
@pytest.mark.parametrize(
    "claim, verified",
    [({}, False), ({"email_verified": False}, False), ({"email_verified": True}, True)],
)
async def test_oidc_signup_verification_follows_claim(users_app, anon_client, claim, verified):
    set_allow_signup(users_app, True)

    assert (await _callback(users_app, anon_client, claim)).status_code == 303
    assert (await find_user(users_app, _EMAIL)).is_verified is verified


@pytest.mark.anyio
async def test_oidc_verified_email_can_link(users_app, anon_client):
    user_id = await seed_password_user(users_app, _EMAIL, is_verified=True)

    assert (await _callback(users_app, anon_client, {"email_verified": True})).status_code == 303
    async with users_app.state.sm.db.session_factory() as session:
        link = (await session.execute(select(OAuthAccount))).scalar_one()
        assert link.user_id == user_id


@pytest.mark.anyio
async def test_oidc_existing_subject_can_sign_in_without_verified_email(users_app, anon_client):
    set_allow_signup(users_app, True)
    assert (await _callback(users_app, anon_client, {})).status_code == 303
    anon_client.cookies.clear()
    set_allow_signup(users_app, False)

    assert (await _callback(users_app, anon_client, {})).status_code == 303


@pytest.mark.anyio
# Google proof comes from People API metadata: test_users_oauth_provider_identity.py.
@pytest.mark.parametrize("provider", ["github", "microsoft"])
async def test_provider_without_email_proof_cannot_link(users_app, anon_client, provider):
    await seed_password_user(users_app, _EMAIL, is_verified=True)

    response = await _callback(users_app, anon_client, {}, provider)

    assert response.status_code == 400
    assert users_app.state.users.settings.cookie_name not in response.cookies


@pytest.mark.anyio
@pytest.mark.parametrize(
    "claim, verified",
    [
        ({}, False),
        ({"email_verified": False}, False),
        ({"email_verified": "true"}, False),
        ({"email_verified": True}, True),
    ],
)
async def test_oidc_identity_preserves_email_proof(claim, verified):
    provider = OAuthProvider("oidc", "OIDC", _ClaimClient(claim))

    assert await provider.get_identity("token") == ("idp-attacker", _EMAIL, verified)


@pytest.mark.anyio
# Google proof comes from People API metadata: test_users_oauth_provider_identity.py.
@pytest.mark.parametrize("provider", ["github", "microsoft"])
async def test_non_oidc_identity_does_not_infer_email_proof(provider):
    client = _ClaimClient({"email_verified": True})

    assert await OAuthProvider(provider, provider, client).get_identity("token") == (
        "idp-attacker",
        _EMAIL,
        False,
    )


@pytest.mark.anyio
async def test_unproven_sso_account_cannot_capture_a_later_verified_login(users_app, anon_client):
    """Pre-hijack: an unproven provider creates the account, a verified one must not join it."""
    set_allow_signup(users_app, True)
    assert (await _callback(users_app, anon_client, {}, "microsoft")).status_code == 303
    assert (await find_user(users_app, _EMAIL)).is_verified is False
    anon_client.cookies.clear()

    response = await _callback(users_app, anon_client, {"email_verified": True})

    assert response.status_code == 403
    assert response.json()["detail"] == "OAUTH_ACCOUNT_NOT_VERIFIED"
    async with users_app.state.sm.db.session_factory() as session:
        providers = {a.oauth_name for a in (await session.execute(select(OAuthAccount))).scalars()}
    assert providers == {"microsoft"}
