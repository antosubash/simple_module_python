"""Microsoft sign-in against a local IdP through the discovery override (#879)."""

from __future__ import annotations

import logging
from urllib.parse import parse_qs, urlparse

import pytest
from _users_oauth_support import find_user, set_allow_signup
from simple_module_test import OidcTestIssuer
from users.core.settings import UsersSettings
from users.oauth import OAuthProvider
from users.oauth.microsoft_dev import MicrosoftDevOidc
from users.oauth.providers import build_client_map

_TENANT = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b"
_OID = "1b2c3d4e-5f60-4a7b-8c9d-0e1f2a3b4c5d"
_CLIENT = "ms-client"


def _settings(**update) -> UsersSettings:
    return UsersSettings(
        oauth_microsoft_client_id=_CLIENT,
        oauth_microsoft_client_secret="secret",
        oauth_microsoft_tenant=_TENANT,
        **update,
    )


@pytest.mark.parametrize("environment", ["development", "testing"])
def test_the_override_applies_in_development_and_tests(monkeypatch, environment):
    monkeypatch.setenv("SM_ENVIRONMENT", environment)
    settings = _settings(oauth_microsoft_discovery_url="http://localhost:8080/.well-known/x")
    assert isinstance(build_client_map(settings)["microsoft"].client, MicrosoftDevOidc)


def test_the_override_is_ignored_in_production(monkeypatch, caplog):
    monkeypatch.setenv("SM_ENVIRONMENT", "production")
    with caplog.at_level(logging.WARNING, logger="users.settings"):
        settings = _settings(
            oauth_microsoft_discovery_url="http://idp.evil/.well-known/x",
            reset_password_token_secret="a-real-reset-secret-for-this-test",
            verification_token_secret="a-real-verify-secret-for-this-test",
        )
    assert "users.oauth.microsoft_discovery_ignored" in caplog.text
    client = build_client_map(settings)["microsoft"].client
    assert not isinstance(client, MicrosoftDevOidc)
    assert client.authorize_endpoint.startswith("https://login.microsoftonline.com/")


def _install(app, issuer: OidcTestIssuer) -> None:
    client = MicrosoftDevOidc(_CLIENT, "secret", _TENANT, issuer.discovery_url)
    app.state.users.oauth_clients["microsoft"] = OAuthProvider(
        "microsoft", "Microsoft", client, trust_email=True
    )


async def _round_trip(client, issuer: OidcTestIssuer, httpx_mock, **claims):
    httpx_mock.add_response(url=issuer.discovery_url, json=issuer.discovery())
    login = await client.get("/api/users/auth/microsoft/login", follow_redirects=False)
    location = urlparse(login.headers["location"])
    query = parse_qs(location.query)
    assert location.geturl().startswith(issuer.authorization_endpoint)
    id_token = issuer.sign(
        {
            "aud": _CLIENT,
            "sub": "pairwise-sub",
            "tid": _TENANT,
            "oid": _OID,
            "preferred_username": "jane@corp.com",
            "name": "Jane Doe",
            "nonce": query["nonce"][0],
            **claims,
        }
    )
    httpx_mock.add_response(
        url=issuer.token_endpoint, json={"access_token": "at", "id_token": id_token}
    )
    httpx_mock.add_response(url=issuer.jwks_url, json=issuer.jwks())
    return await client.get(
        f"/api/users/auth/microsoft/callback?code=abc&state={query['state'][0]}",
        follow_redirects=False,
    )


@pytest.mark.anyio
async def test_a_full_sign_in_against_a_local_issuer(users_app, anon_client, httpx_mock):
    set_allow_signup(users_app, True)
    issuer = OidcTestIssuer("https://idp.test/realms/entra")
    _install(users_app, issuer)

    resp = await _round_trip(anon_client, issuer, httpx_mock)

    assert resp.status_code == 303
    user = await find_user(users_app, "jane@corp.com")
    assert user is not None and user.is_verified and user.full_name == "Jane Doe"


@pytest.mark.anyio
async def test_a_token_from_another_issuer_is_refused(users_app, anon_client, httpx_mock):
    set_allow_signup(users_app, True)
    issuer = OidcTestIssuer("https://idp.test/realms/entra")
    _install(users_app, issuer)

    resp = await _round_trip(anon_client, issuer, httpx_mock, iss="https://idp.test/realms/other")

    assert resp.json()["detail"] == "OAUTH_PROVIDER_ERROR"
    assert await find_user(users_app, "jane@corp.com") is None
