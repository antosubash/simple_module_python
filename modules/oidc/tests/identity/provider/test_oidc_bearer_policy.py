"""A browser ID token cannot authenticate the configured resource-server API."""

import pytest
from oidc_flow_helpers import _AUDIENCE, _sign_id_token
from starlette.requests import Request


@pytest.mark.parametrize("audience,accepted", [("my-app", False), ("api", True), ("graph", False)])
async def test_signed_bearer_purpose(oidc_app, audience, accepted):
    provider = oidc_app.state.auth.auth_provider
    token = _sign_id_token(nonce="unused", aud=audience, azp=_AUDIENCE)
    request = Request(
        {
            "type": "http",
            "app": oidc_app,
            "headers": [(b"authorization", f"bearer {token}".encode())],
        }
    )
    principal = await provider.resolve_user(request)
    assert (principal is not None) is accepted
    if principal:
        assert principal.auth_kind == "bearer"
        assert principal.tenant_id is None
        assert principal.roles == ["admin"]


def _bearer_request(app, token):
    return Request(
        {"type": "http", "app": app, "headers": [(b"authorization", f"Bearer {token}".encode())]}
    )


@pytest.mark.parametrize(
    "client_claims,allowed,accepted",
    [
        ({"azp": _AUDIENCE}, [], True),  # our own client
        ({"azp": "other-spa"}, [], False),  # any other client of the IdP
        ({"azp": "other-spa"}, ["other-spa"], True),  # explicitly allowed
        ({"appid": "other-spa"}, ["other-spa"], True),  # Entra v1 names it appid
        ({}, [_AUDIENCE], False),  # no client named: fail closed
    ],
)
async def test_api_tokens_only_from_allowed_clients(oidc_app, client_claims, allowed, accepted):
    oidc_app.state.oidc.settings.api_allowed_client_ids = allowed
    token = _sign_id_token(nonce="unused", aud="api", **client_claims)
    principal = await oidc_app.state.auth.auth_provider.resolve_user(
        _bearer_request(oidc_app, token)
    )
    assert (principal is not None) is accepted
