"""Bootstrap credentials are only sent to direct loopback development clients (#1229)."""

from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from simple_module_hosting.frontend.inertia_deps import get_inertia
from simple_module_inertia import (
    Inertia,
    InertiaConfig,
    InertiaMiddleware,
    inertia_dependency_factory,
)
from simple_module_test import inertia_page
from starlette.middleware.sessions import SessionMiddleware
from users.auth_local.views import login_page
from users.core.settings import UsersSettings
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware


@pytest.fixture
def login_app(tmp_path, monkeypatch):
    monkeypatch.setenv("SM_USERS_BOOTSTRAP_EMAIL", "bootstrap-admin@example.com")
    monkeypatch.setenv("SM_USERS_BOOTSTRAP_PASSWORD", "AdminPass1!")
    monkeypatch.setenv("SM_USERS_BOOTSTRAP_USER_EMAIL", "bootstrap-user@example.com")
    monkeypatch.setenv("SM_USERS_BOOTSTRAP_USER_PASSWORD", "UserPass1!")

    # Exercise the real login route and Inertia serialization without database startup.
    app = FastAPI()
    app.state.host = SimpleNamespace(settings=SimpleNamespace(login_redirect_url="/home/"))
    app.state.users = SimpleNamespace(settings=UsersSettings(), oauth_providers=[])
    app.state.sm = SimpleNamespace(settings=SimpleNamespace(is_development=True), modules=[])
    (tmp_path / "index.html").write_text(
        "<!doctype html><html><body>{% inertia_body %}</body></html>"
    )
    config = InertiaConfig(templates=Jinja2Templates(directory=tmp_path), version="test")
    dependency = inertia_dependency_factory(config)

    async def inertia_dependency(request: Request) -> Inertia:
        return dependency(request)

    app.dependency_overrides[get_inertia] = inertia_dependency
    app.add_middleware(InertiaMiddleware)
    app.add_middleware(SessionMiddleware, secret_key="test")
    app.add_api_route("/users/login", login_page, response_model=None)
    return app


@pytest.mark.parametrize("inertia", [False, True], ids=["html", "json"])
@pytest.mark.parametrize(
    ("host", "forwarded", "trusted_proxy", "environment", "visible"),
    [
        ("127.0.0.1", None, False, "development", True),
        ("127.42.0.9", None, False, "development", True),
        ("127.255.255.255", None, False, "development", True),
        ("::1", None, False, "development", True),
        ("::ffff:127.0.0.1", None, False, "development", True),
        ("::ffff:7f2a:9", None, False, "development", True),
        ("192.168.1.20", None, False, "development", False),
        ("203.0.113.20", None, False, "development", False),
        ("2001:db8::1", None, False, "development", False),
        ("::ffff:192.168.1.20", None, False, "development", False),
        ("126.255.255.255", None, False, "development", False),
        ("128.0.0.1", None, False, "development", False),
        (None, None, False, "development", False),
        ("", None, False, "development", False),
        ("/tmp/uvicorn.sock", None, False, "development", False),
        ("unix", None, False, "development", False),
        ("localhost", None, False, "development", False),
        ("invalid", None, False, "development", False),
        ("127.0.0.1", "203.0.113.20", False, "development", False),
        ("127.0.0.1", "127.0.0.1", False, "development", False),
        ("127.0.0.1", "", False, "development", False),
        ("::1", "::1", False, "development", False),
        ("127.0.0.1", "203.0.113.20", True, "development", False),
        ("127.0.0.1", "127.0.0.1", True, "development", False),
        ("127.0.0.1", "", True, "development", False),
        ("127.0.0.1", None, False, "production", False),
        ("::1", None, False, "production", False),
        ("127.0.0.1", None, False, "testing", False),
    ],
)
async def test_login_bootstrap_credentials_visibility(
    login_app, host, forwarded, trusted_proxy, environment, visible, inertia
):
    app = login_app
    app.state.sm.settings.is_development = environment == "development"
    if trusted_proxy:
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["127.0.0.1"])
    headers = {"X-Inertia": "true", "X-Inertia-Version": "test"} if inertia else {}
    if forwarded is not None:
        headers["X-Forwarded-For"] = forwarded
    transport = httpx.ASGITransport(app=app, client=(host, 12345) if host is not None else None)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/users/login", headers=headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/json" if inertia else "text/html"
    )
    page = inertia_page(response)
    assert page.component == "Users/Login"
    if visible:
        assert page.props["dev_accounts"] == [
            {"label": "Admin", "email": "bootstrap-admin@example.com", "password": "AdminPass1!"},
            {"label": "User", "email": "bootstrap-user@example.com", "password": "UserPass1!"},
        ]
    else:
        assert not page.props.get("dev_accounts")
        for secret in (
            "bootstrap-admin@example.com",
            "AdminPass1!",
            "bootstrap-user@example.com",
            "UserPass1!",
        ):
            assert secret not in response.text


@pytest.mark.parametrize("inertia", [False, True], ids=["html", "json"])
@pytest.mark.parametrize(
    ("header", "value"),
    [
        ("Forwarded", "for=203.0.113.20;proto=https"),
        ("Forwarded", ""),
        ("X-Real-IP", "203.0.113.20"),
        ("X-Real-IP", "127.0.0.1"),
        ("X-Real-IP", ""),
        ("X-Forwarded-Proto", "https"),
        ("X-Forwarded-Host", "public.example.com"),
    ],
)
async def test_login_no_credentials_through_loopback_proxy(login_app, header, value, inertia):
    headers = {header: value}
    if inertia:
        headers.update({"X-Inertia": "true", "X-Inertia-Version": "test"})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=login_app), base_url="http://testserver"
    ) as client:
        response = await client.get("/users/login", headers=headers)

    assert response.status_code == 200
    assert inertia_page(response).props["dev_accounts"] == []
    assert "AdminPass1!" not in response.text
    assert "UserPass1!" not in response.text


@pytest.mark.parametrize(
    "partial_headers",
    [
        {"X-Inertia-Partial-Data": "allow_signup"},
        {"X-Inertia-Partial-Except": "dev_accounts"},
        {"X-Inertia-Partial-Data": "dev_accounts.password"},
    ],
)
@pytest.mark.parametrize("denial", ["remote", "forwarded", "production"])
async def test_login_partial_reload_clears_cached_credentials(login_app, partial_headers, denial):
    headers = {"X-Inertia": "true", "X-Inertia-Version": "test"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=login_app), base_url="http://testserver"
    ) as client:
        initial = await client.get("/users/login", headers=headers)
        assert inertia_page(initial).props["dev_accounts"]

        if denial == "production":
            login_app.state.sm.settings.is_development = False
        if denial == "forwarded":
            headers["X-Forwarded-For"] = "203.0.113.20"
        headers.update({"X-Inertia-Partial-Component": "Users/Login", **partial_headers})
        transport = httpx.ASGITransport(
            app=login_app, client=("203.0.113.20" if denial == "remote" else "127.0.0.1", 12345)
        )
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as other:
            response = await other.get("/users/login", headers=headers)

    assert response.status_code == 200
    assert inertia_page(response).props["dev_accounts"] == []
    assert "AdminPass1!" not in response.text
    assert "UserPass1!" not in response.text


@pytest.mark.parametrize("inertia", [False, True], ids=["html", "json"])
async def test_login_credentials_cannot_be_stored_in_http_cache(login_app, inertia):
    headers = {"X-Inertia": "true", "X-Inertia-Version": "test"} if inertia else {}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=login_app), base_url="http://testserver"
    ) as client:
        response = await client.get("/users/login", headers=headers)

    assert response.status_code == 200
    assert inertia_page(response).props["dev_accounts"]
    assert response.headers.get("cache-control") == "private, no-store"


async def test_login_remote_spoofed_loopback_rejected_with_trust_all(login_app):
    login_app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
    headers = {
        "X-Inertia": "true",
        "X-Inertia-Version": "test",
        "X-Forwarded-For": "::ffff:127.0.0.1",
    }
    transport = httpx.ASGITransport(app=login_app, client=("203.0.113.20", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        response = await client.get("/users/login", headers=headers)

    assert response.status_code == 200
    assert inertia_page(response).props["dev_accounts"] == []


@pytest.mark.parametrize("value", ["", "false"])
async def test_login_inertia_header_presence_cannot_expose_remote_credentials(login_app, value):
    headers = {"X-Inertia": value, "X-Inertia-Version": "test"}
    transport = httpx.ASGITransport(app=login_app, client=("203.0.113.20", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/users/login", headers=headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert inertia_page(response).props["dev_accounts"] == []
