"""A browser ID token cannot authenticate the configured resource-server API."""

import pytest
from oidc_flow_helpers import _sign_id_token
from starlette.requests import Request


@pytest.mark.parametrize("audience,accepted", [("my-app", False), ("api", True), ("graph", False)])
async def test_signed_bearer_purpose(oidc_app, audience, accepted):
    provider = oidc_app.state.auth.auth_provider
    token = _sign_id_token(nonce="unused", aud=audience)
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
