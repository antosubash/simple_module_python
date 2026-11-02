"""Discovery is a strict boot dependency outside development; dev login retries."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from oidc.module import OidcModule
from oidc.provider import OidcAuthProvider
from oidc.runtime import require_client
from oidc.settings import OidcSettings
from oidc.state import OidcState
from starlette.requests import Request


def _app(environment):
    state = OidcState(
        settings=OidcSettings(
            discovery_url="https://idp/.well-known/openid-configuration", client_id="app"
        )
    )
    provider = OidcAuthProvider(state=state)
    return SimpleNamespace(
        state=SimpleNamespace(
            oidc=state,
            auth=SimpleNamespace(auth_provider=provider),
            sm=SimpleNamespace(settings=SimpleNamespace(environment=environment)),
        )
    )


@pytest.mark.parametrize("environment", ["testing", "staging", "production"])
async def test_discovery_failure_refuses_non_development_boot(httpx_mock, environment):
    httpx_mock.add_response(status_code=503)
    with pytest.raises(RuntimeError, match="OIDC discovery failed"):
        await OidcModule().on_startup(_app(environment))


async def test_development_retries_lazily_and_single_flight(httpx_mock):
    app = _app("development")
    httpx_mock.add_exception(httpx.ConnectError("offline"))
    await OidcModule().on_startup(app)
    assert app.state.oidc.client is None
    httpx_mock.add_response(
        json={
            "issuer": "https://idp",
            "authorization_endpoint": "https://login/authorize",
            "token_endpoint": "https://tokens/token",
            "jwks_uri": "https://keys/jwks",
        }
    )
    request = Request({"type": "http", "app": app})
    clients = await asyncio.gather(*[require_client(request) for _ in range(5)])
    assert all(client is clients[0] for client in clients)
    assert len(httpx_mock.get_requests()) == 2


async def test_mismatched_discovery_issuer_refuses_boot(httpx_mock):
    httpx_mock.add_response(
        json={
            "issuer": "https://other",
            "authorization_endpoint": "https://idp/authorize",
            "token_endpoint": "https://idp/token",
            "jwks_uri": "https://idp/jwks",
        }
    )
    with pytest.raises(RuntimeError):
        await OidcModule().on_startup(_app("testing"))
