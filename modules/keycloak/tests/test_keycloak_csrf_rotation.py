"""A successful OIDC callback must discard the previous principal's CSRF token."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from keycloak.endpoints import api
from simple_module_hosting.csrf import get_csrf_token
from starlette.requests import Request


async def test_oidc_callback_rotates_csrf(monkeypatch):
    context = SimpleNamespace(to_session_dict=lambda: {"id": "new-user"})
    provider = SimpleNamespace(
        _upsert_user_cache=AsyncMock(return_value="new-user"),
        _claims_to_user_context=lambda claims, cache_id: context,
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            keycloak=SimpleNamespace(
                settings=SimpleNamespace(login_redirect_url="/dashboard/"),
                jwks_cache=SimpleNamespace(validate_jwt=AsyncMock(return_value={"sub": "new"})),
            ),
            auth=SimpleNamespace(auth_provider=provider),
        )
    )
    request = Request(
        {
            "type": "http",
            "app": app,
            "query_string": b"code=code&state=valid",
            "session": {"keycloak_oidc_state": "valid", "next": "/deep-link/"},
        }
    )
    request.url_for = lambda name: "https://test/callback"
    monkeypatch.setattr(
        api,
        "_get_oidc_client",
        lambda req: SimpleNamespace(
            exchange_code=AsyncMock(return_value={"access_token": "access", "id_token": "id"})
        ),
    )
    old = get_csrf_token(request)
    response = await api.oidc_callback(request)
    assert response.headers["location"] == "/deep-link/"
    assert request.session["user_ctx"] == {"id": "new-user"}
    assert get_csrf_token(request) != old
