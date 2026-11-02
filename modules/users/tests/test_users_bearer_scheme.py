"""The ``Authorization`` scheme is case-insensitive (RFC 9110 §11.1, GH #533).

``/auth/token`` used to answer ``token_type="bearer"``, and a client that built
its header from that value sent ``bearer <token>`` — which the provider refused.
"""

from __future__ import annotations

import pytest
from starlette.requests import Request

_TOKEN = "/api/users/auth/token"


def _request(app, header: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/anything",
            "headers": [(b"authorization", header.encode())],
            "session": {},
            "app": app,
        }
    )


@pytest.mark.anyio
@pytest.mark.parametrize("scheme", ["Bearer", "bearer", "BEARER", "  bearer  "])
async def test_any_scheme_casing_authenticates(users_app, anon_client, scheme):
    from users.provider import UsersAuthProvider

    resp = await anon_client.post(
        _TOKEN, json={"email": "admin@example.com", "password": "AdminPass1!"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "Bearer"

    provider = UsersAuthProvider()
    request = _request(users_app, f"{scheme} {body['access_token']}")
    assert provider.is_bearer_request(request)
    ctx = await provider.resolve_user(request)
    assert ctx is not None
    assert ctx.email == "admin@example.com"


@pytest.mark.anyio
async def test_another_scheme_is_not_a_bearer_request(users_app):
    from users.provider import UsersAuthProvider

    request = _request(users_app, "Basic dXNlcjpwYXNz")
    assert not UsersAuthProvider().is_bearer_request(request)
    assert await UsersAuthProvider().resolve_user(request) is None
