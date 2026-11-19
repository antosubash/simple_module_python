"""Built-ins keep their configuration and endpoints through the registry."""

from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from users.core.settings import UsersSettings


@pytest.mark.anyio
async def test_registry_builds_all_builtins_with_existing_callbacks_and_pkce(httpx_mock):
    from users.core.startup import _build_oauth_clients

    httpx_mock.add_response(
        url="https://idp.example/.well-known/openid-configuration",
        json={
            "authorization_endpoint": "https://idp.example/authorize",
            "token_endpoint": "https://idp.example/token",
            "userinfo_endpoint": "https://idp.example/userinfo",
        },
    )
    settings = UsersSettings(
        oauth_google_client_id="google-id",
        oauth_google_client_secret="google-secret",
        oauth_github_client_id="github-id",
        oauth_github_client_secret="github-secret",
        oauth_microsoft_client_id="ms-id",
        oauth_microsoft_client_secret="ms-secret",
        oauth_microsoft_tenant="6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b",
        oauth_microsoft_trust_tenant_upn=True,
        oauth_trusted_email_domains={"microsoft": ["staff.example"]},
        oauth_oidc_client_id="oidc-id",
        oauth_oidc_client_secret="oidc-secret",
        oauth_oidc_discovery_url="https://idp.example/.well-known/openid-configuration",
        oauth_oidc_display_name="Company SSO",
    )
    app = FastAPI()
    app.state.users = SimpleNamespace(settings=settings)
    _build_oauth_clients(app)

    assert app.state.users.oauth_providers == [
        {"name": "google", "display_name": "Google"},
        {"name": "github", "display_name": "GitHub"},
        {"name": "microsoft", "display_name": "Microsoft"},
        {"name": "oidc", "display_name": "Company SSO"},
    ]
    microsoft = app.state.users.oauth_clients["microsoft"]
    assert microsoft.uses_pkce is True
    assert microsoft.trust_email is True
    assert microsoft.trusted_domains == frozenset({"staff.example"})
    for name, provider in app.state.users.oauth_clients.items():
        callback = f"https://app.example/api/users/auth/{name}/callback"
        login = {"verifier": "test-verifier", "nonce": "test-nonce"} if provider.uses_pkce else None
        url = await provider.authorization_url(callback, "test-state", login)
        query = parse_qs(urlsplit(url).query)
        assert query["redirect_uri"] == [callback]
        assert query["state"] == ["test-state"]
        if name == "microsoft":
            assert query["code_challenge_method"] == ["S256"]
            assert query["nonce"] == ["test-nonce"]


@pytest.mark.parametrize("discovery_fails", [False, True])
def test_incomplete_or_failed_oidc_discovery_is_hidden(httpx_mock, discovery_fails):
    from users.core.startup import _build_oauth_clients

    settings = UsersSettings(oauth_oidc_client_id="oidc-id", oauth_oidc_client_secret="secret")
    if discovery_fails:
        settings = settings.model_copy(
            update={
                "oauth_oidc_discovery_url": "https://idp.example/.well-known/openid-configuration"
            }
        )
        httpx_mock.add_response(
            url="https://idp.example/.well-known/openid-configuration", status_code=503
        )
    app = FastAPI()
    app.state.users = SimpleNamespace(settings=settings)
    _build_oauth_clients(app)
    assert app.state.users.oauth_clients == {}
    assert app.state.users.oauth_providers == []
