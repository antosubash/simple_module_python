"""Browser cookies cannot carry authority across providers or OIDC configurations."""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from auth.contracts.schemas import UserContext
from keycloak.core.settings import KeycloakSettings
from keycloak.identity.provider import KeycloakAuthProvider
from oidc.provider import OidcAuthProvider
from oidc.settings import OidcSettings
from simple_module_hosting.session import SessionMiddleware
from starlette.requests import Request


@pytest.fixture(params=["oidc", "keycloak"])
def authority_provider(request):
    if request.param == "oidc":
        provider = OidcAuthProvider(
            OidcSettings(
                discovery_url="https://issuer.test/.well-known/openid-configuration",
                client_id="app",
                client_secret="secret",
            )
        )
    else:
        provider = KeycloakAuthProvider(
            KeycloakSettings(
                server_url="https://issuer.test",
                realm="test",
                client_id="app",
                client_secret="secret",
            )
        )
    provider.jwks_cache = SimpleNamespace(
        issuer="https://issuer.test", validate_jwt=AsyncMock(return_value=None)
    )
    return provider


def browser_request(provider, *, own_identity=True):
    session = {
        "user_ctx": UserContext(
            id="subject", email="admin@example.com", name="Admin", roles=["admin"]
        ).to_session_dict(),
        "expires_at": int(time.time()) + 300,
    }
    if own_identity:
        session[f"{provider.name}_identity"] = ["https://issuer.test", "subject"]
    return Request({"type": "http", "headers": [], "session": session})


async def test_legacy_own_identity_is_stamped_and_matching_cookie_stays_signed_in(
    authority_provider,
):
    provider = authority_provider
    req = browser_request(provider)
    assert (await provider.resolve_user(req)).roles == ["admin"]
    marker = req.session.get("oidc_authority")
    assert isinstance(marker, str) and 16 <= len(marker) <= 64
    assert (await provider.resolve_user(req)).id == "subject"
    assert req.session["oidc_authority"] == marker
    provider.jwks_cache.validate_jwt.assert_not_awaited()


@pytest.mark.parametrize("change", ["client", "issuer", "provider"])
async def test_changed_authority_clears_cookie(authority_provider, change):
    provider = authority_provider
    req = browser_request(provider)
    assert await provider.resolve_user(req) is not None
    if change == "client":
        provider._settings.client_id = "another-client"
    elif change == "issuer":
        if provider.name == "oidc":
            provider._settings.discovery_url = "https://other.test/.well-known/openid-configuration"
        else:
            provider._settings.realm = "another-realm"
    else:
        provider = (
            KeycloakAuthProvider(KeycloakSettings())
            if provider.name == "oidc"
            else OidcAuthProvider(OidcSettings())
        )
    assert await provider.resolve_user(req) is None
    assert req.session == {}


async def test_other_provider_legacy_identity_is_rejected(authority_provider):
    req = browser_request(authority_provider, own_identity=False)
    other = "keycloak" if authority_provider.name == "oidc" else "oidc"
    req.session[f"{other}_identity"] = ["https://issuer.test", "subject"]
    assert await authority_provider.resolve_user(req) is None
    assert req.session == {}


async def test_real_users_login_cookie_is_anonymous_after_provider_switch(
    authority_provider,
    db_state,
    db_session,
):
    from fastapi import FastAPI
    from users.db_adapter import UserDatabaseWithRoles
    from users.manager import UserManager
    from users.models import OAuthAccount, Role, User
    from users.provider import UsersAuthProvider, clear_session_version_cache
    from users.settings import UsersSettings

    role = Role(name="admin")
    user = User(email="authority@example.com", is_verified=True, roles=[role])
    db_session.add(role)
    db_session.add(user)
    await db_session.commit()
    app = FastAPI()
    config = UsersSettings.model_construct()
    app.state.sm = SimpleNamespace(db=db_state)
    app.state.users = SimpleNamespace(settings=config)
    app.state.auth = SimpleNamespace(auth_provider=UsersAuthProvider())
    app.add_middleware(SessionMiddleware, secret_key="test-authority-secret", https_only=False)

    @app.post("/login")
    async def login(request: Request):
        adapter = UserDatabaseWithRoles(db_session, User, OAuthAccount)
        await UserManager(adapter, SimpleNamespace(), config).on_after_login(user, request)
        ctx = await app.state.auth.auth_provider.resolve_user(request)
        return {"roles": ctx.roles}

    @app.get("/who")
    async def who(request: Request):
        ctx = await app.state.auth.auth_provider.resolve_user(request)
        return {"authenticated": ctx is not None, "session": dict(request.session)}

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (await client.post("/login")).json()["roles"] == ["admin"]
            assert client.cookies.get("session")
            app.state.auth.auth_provider = authority_provider
            for _ in range(3):
                assert (await client.get("/who")).json() == {"authenticated": False, "session": {}}
            client.cookies.clear()
            assert not (await client.get("/who")).json()["authenticated"]
        authority_provider.jwks_cache.validate_jwt.assert_not_awaited()
    finally:
        clear_session_version_cache()


async def test_anonymous_login_transaction_survives_resolution(authority_provider):
    req = browser_request(authority_provider, own_identity=False)
    req.session.clear()
    req.session.update({f"{authority_provider.name}_state": "pending", "next": "/deep-link"})
    before = dict(req.session)
    assert await authority_provider.resolve_user(req) is None
    assert req.session == before


async def test_secret_rotation_does_not_change_public_authority(authority_provider):
    req = browser_request(authority_provider)
    assert await authority_provider.resolve_user(req) is not None
    marker = req.session["oidc_authority"]
    authority_provider._settings.client_secret = "rotated-secret"
    assert await authority_provider.resolve_user(req) is not None
    assert req.session["oidc_authority"] == marker


async def test_pre_750_keycloak_cookie_with_its_refresh_token_stays_signed_in():
    provider = KeycloakAuthProvider(
        KeycloakSettings(
            server_url="https://issuer.test", realm="test", client_id="app", client_secret="s"
        )
    )
    provider.jwks_cache = SimpleNamespace(validate_jwt=AsyncMock(return_value=None))
    req = browser_request(provider, own_identity=False)
    req.session["keycloak_refresh_token"] = "sealed-by-keycloak"
    assert (await provider.resolve_user(req)).roles == ["admin"]
    assert req.session.get("oidc_authority")
    # The generic provider's refresh token proves nothing to Keycloak.
    other = browser_request(provider, own_identity=False)
    other.session["oidc_refresh_token"] = "sealed-by-oidc"
    assert await provider.resolve_user(other) is None
    assert "user_ctx" not in other.session
