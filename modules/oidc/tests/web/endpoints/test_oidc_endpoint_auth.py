"""Discovery-driven authentication for token grants and refresh-token revocation."""

import base64
from types import SimpleNamespace
from urllib.parse import parse_qs

import httpx
import pytest
from oidc.core.constants import SESSION_REFRESH_TOKEN_KEY
from oidc.core.runtime import initialize
from oidc.core.settings import OidcSettings
from oidc.core.state import OidcState
from oidc.identity.tokens import seal_refresh_token
from starlette.requests import Request

_DOC = {
    "issuer": "https://idp",
    "authorization_endpoint": "https://idp/authorize",
    "token_endpoint": "https://idp/token",
    "jwks_uri": "https://idp/keys",
    "end_session_endpoint": "https://idp/logout",
}


@pytest.fixture
async def endpoint_app(httpx_mock, request):
    state = OidcState(
        settings=OidcSettings(
            discovery_url="https://idp/.well-known/openid-configuration",
            client_id="app :+é",
            client_secret="secret :+é",
        )
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            oidc=state,
            auth=SimpleNamespace(auth_provider=SimpleNamespace()),
            sm=SimpleNamespace(
                settings=SimpleNamespace(environment="testing", secret_key="test-secret")
            ),
        )
    )
    httpx_mock.add_response(json={**_DOC, **getattr(request, "param", {})})
    assert await initialize(app)
    return app


def _assert_auth(sent, *, basic):
    data = parse_qs(sent.content.decode())
    if basic:
        encoded = sent.headers["authorization"].removeprefix("Basic ")
        assert base64.b64decode(encoded).decode() == "app+%3A%2B%C3%A9:secret+%3A%2B%C3%A9"
        assert "client_id" not in data
        assert "client_secret" not in data
    else:
        assert "authorization" not in sent.headers
        assert data.pop("client_id") == ["app :+é"]
        assert data.pop("client_secret") == ["secret :+é"]
    assert sent.headers["content-type"] == "application/x-www-form-urlencoded"
    assert sent.extensions["timeout"]["read"] <= 10
    return data


@pytest.mark.parametrize(
    "endpoint_app,basic",
    [
        ({}, False),
        ({"token_endpoint_auth_methods_supported": ["client_secret_post"]}, False),
        (
            {
                "token_endpoint_auth_methods_supported": [
                    "client_secret_basic",
                    "client_secret_post",
                ]
            },
            False,
        ),
        ({"token_endpoint_auth_methods_supported": ["client_secret_basic"]}, True),
    ],
    indirect=["endpoint_app"],
)
@pytest.mark.parametrize("grant", ["code", "refresh"])
async def test_discovered_client_auth_for_both_grants(endpoint_app, basic, grant, httpx_mock):
    httpx_mock.add_response(url="https://idp/token", json={"id_token": "new"})
    client = endpoint_app.state.oidc.client
    if grant == "code":
        result = await client.exchange_code("code", "https://app/cb", code_verifier="verifier")
        expected = {
            "grant_type": ["authorization_code"],
            "code": ["code"],
            "redirect_uri": ["https://app/cb"],
            "code_verifier": ["verifier"],
        }
    else:
        result = await client.refresh_tokens("refresh")
        expected = {"grant_type": ["refresh_token"], "refresh_token": ["refresh"]}
    assert result == {"id_token": "new"}
    assert _assert_auth(httpx_mock.get_requests()[-1], basic=basic) == expected


def _logout_request(app, session):
    return Request(
        {
            "type": "http",
            "app": app,
            "session": session,
            "headers": [(b"host", b"app")],
            "scheme": "https",
            "server": ("app", 443),
            "path": "/oidc/logout",
            "root_path": "",
        }
    )


@pytest.mark.parametrize(
    "endpoint_app,basic",
    [
        ({"revocation_endpoint": "https://idp/revoke"}, False),
        (
            {
                "revocation_endpoint": "https://idp/revoke",
                "token_endpoint_auth_methods_supported": ["client_secret_basic"],
            },
            True,
        ),
    ],
    indirect=["endpoint_app"],
)
@pytest.mark.parametrize("failure", [None, "http", "network"])
async def test_logout_revokes_before_clearing_even_on_failure(
    endpoint_app, basic, failure, httpx_mock, caplog
):
    from oidc.web.endpoints.views import logout

    session = {SESSION_REFRESH_TOKEN_KEY: seal_refresh_token(endpoint_app, "private-refresh")}
    calls = []

    def revoke(sent):
        assert SESSION_REFRESH_TOKEN_KEY in session
        calls.append(sent)
        if failure == "network":
            raise httpx.ConnectError("private-refresh response-body-secret")
        return httpx.Response(503 if failure else 200, text="private-refresh response-body-secret")

    httpx_mock.add_callback(revoke, url="https://idp/revoke", is_optional=True)
    response = await logout(_logout_request(endpoint_app, session))
    assert session == {}
    assert response.status_code == 303
    assert response.headers["location"].startswith("https://idp/logout?")
    assert len(calls) == 1
    assert _assert_auth(calls[0], basic=basic) == {
        "token": ["private-refresh"],
        "token_type_hint": ["refresh_token"],
    }
    assert "private-refresh" not in caplog.text
    assert "response-body-secret" not in caplog.text


@pytest.mark.parametrize(
    "endpoint_app,token",
    [
        ({}, "sealed"),
        ({"revocation_endpoint": "https://idp/revoke"}, None),
        ({"revocation_endpoint": "https://idp/revoke"}, "tampered"),
    ],
    indirect=["endpoint_app"],
)
async def test_logout_skips_unavailable_revocation(endpoint_app, token, httpx_mock):
    from oidc.web.endpoints.views import logout

    session = {}
    if token:
        session[SESSION_REFRESH_TOKEN_KEY] = (
            seal_refresh_token(endpoint_app, "refresh") if token == "sealed" else token
        )
    response = await logout(_logout_request(endpoint_app, session))
    assert response.status_code == 303
    assert session == {}
    assert len(httpx_mock.get_requests()) == 1  # Discovery only.


@pytest.mark.parametrize(
    "endpoint_app",
    [
        {
            "revocation_endpoint": "https://idp/revoke",
            "token_endpoint_auth_methods_supported": ["client_secret_post"],
            "revocation_endpoint_auth_methods_supported": ["client_secret_basic"],
        }
    ],
    indirect=["endpoint_app"],
)
async def test_revocation_uses_its_own_advertised_auth_method(endpoint_app, httpx_mock):
    httpx_mock.add_response(url="https://idp/revoke", text="")
    await endpoint_app.state.oidc.client.revoke_refresh_token("refresh")
    assert _assert_auth(httpx_mock.get_requests()[-1], basic=True) == {
        "token": ["refresh"],
        "token_type_hint": ["refresh_token"],
    }


async def test_revocation_total_time_is_capped(endpoint_app, monkeypatch):
    import asyncio

    from oidc.identity import client as client_module

    async def hang(*args, **kwargs):
        await asyncio.Event().wait()  # an IdP that never answers

    client = endpoint_app.state.oidc.client
    monkeypatch.setattr(client_module, "_REVOKE_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(client, "_revocation_endpoint", "https://idp.test/revoke")
    monkeypatch.setattr(client, "_post", hang)
    with pytest.raises(TimeoutError):
        await client.revoke_refresh_token("refresh")
