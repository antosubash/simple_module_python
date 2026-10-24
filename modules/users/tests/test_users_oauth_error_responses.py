"""Exercise callback error responses without a database or provider network."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import APIRouter, FastAPI
from fastapi_users.exceptions import UserNotExists
from httpx_oauth.exceptions import GetProfileError
from starlette.middleware.sessions import SessionMiddleware
from users.deps import auth_backend, get_user_manager
from users.oauth.api import register_oauth_routes
from users.oauth.providers import OAuthProvider


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("failure", "detail", "public_code", "status"),
    [
        ("unverified", "OAUTH_ACCOUNT_NOT_VERIFIED", "account_not_verified", 403),
        ("signup", "OAUTH_SIGNUP_DISABLED", "signup_disabled", 403),
        ("provider", "OAUTH_PROVIDER_ERROR", "signin_failed", 400),
        ("profile", "OAUTH_PROVIDER_ERROR", "signin_failed", 400),
        ("token", "OAUTH_PROVIDER_ERROR", "signin_failed", 400),
        ("state", "OAUTH_INVALID_STATE", "signin_failed", 400),
        ("missing_code", "OAUTH_MISSING_CODE", "signin_failed", 400),
    ],
)
@pytest.mark.parametrize("accept", ["text/html", "application/json", "*/*", "xhr"])
async def test_oauth_callback_error_response(failure, detail, public_code, status, accept):
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret")
    provider_client = AsyncMock()
    provider_client.get_authorization_url.side_effect = lambda url, state: (
        f"https://idp/?state={state}"
    )
    provider_client.get_access_token.return_value = {"access_token": "test-token"}
    provider_client.get_profile.return_value = {"sub": "test-id", "email": "test@example.com"}
    if failure == "token":
        provider_client.get_access_token.side_effect = httpx.ConnectError("private details")
    if failure == "profile":
        provider_client.get_profile.side_effect = GetProfileError("private provider details")
    app.state.users = SimpleNamespace(
        oauth_clients={"oidc": OAuthProvider("oidc", "OIDC", provider_client)},
        settings=SimpleNamespace(allow_signup=False),
    )
    manager = AsyncMock()
    manager.get_by_oauth_account.side_effect = UserNotExists()
    if failure == "unverified":
        manager.get_by_email.return_value = SimpleNamespace(is_verified=False, invited_at=None)
    else:
        manager.get_by_email.side_effect = UserNotExists()

    async def manager_dep():
        return manager

    async def strategy_dep():
        return None

    app.dependency_overrides[get_user_manager] = manager_dep
    app.dependency_overrides[auth_backend.get_strategy] = strategy_dep
    router = APIRouter(prefix="/api/users")
    register_oauth_routes(router)
    app.include_router(router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        login = await client.get("/api/users/auth/oidc/login")
        state = httpx.URL(login.headers["location"]).params["state"]
        params = {"state": "bad" if failure == "state" else state}
        if failure == "provider":
            params["error"] = "<script>untrusted provider text</script>"
        elif failure != "missing_code":
            params["code"] = "test-code"
        headers = {"accept": accept}
        if accept == "xhr":
            headers = {"accept": "text/html", "x-requested-with": "XMLHttpRequest"}
        response = await client.get("/api/users/auth/oidc/callback", params=params, headers=headers)
    if accept == "text/html":
        assert response.status_code == 303
        assert response.headers["location"] == f"/users/login?oauth_error={public_code}"
    else:
        assert response.status_code == status
        assert response.json() == {"detail": detail}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "code", ["account_not_verified", "signup_disabled", "signin_failed", "<script>"]
)
async def test_login_view_filters_oauth_error_codes(code):
    from starlette.requests import Request
    from users.auth_local.views import login_page
    from users.settings import UsersSettings

    app = FastAPI()
    app.state.users = SimpleNamespace(settings=UsersSettings(), oauth_providers=[])
    app.state.sm = SimpleNamespace(settings=SimpleNamespace(is_development=False), modules=[])
    request = Request(
        {
            "type": "http",
            "app": app,
            "session": {},
            "query_string": str(httpx.QueryParams({"oauth_error": code})).encode(),
        }
    )
    inertia = SimpleNamespace(render=AsyncMock())
    await login_page(request, inertia)
    props = inertia.render.call_args.args[1]
    assert props["oauth_error"] == (None if code == "<script>" else code)
