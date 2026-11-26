"""A temporary discovery outage must not disable configured SSO (#1226)."""

import asyncio
import logging
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import APIRouter, FastAPI
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import Response
from users.core.settings import UsersSettings
from users.core.startup import _build_oauth_clients
from users.oauth.api import register_oauth_routes

DISCOVERY_URL = "https://idp.example/.well-known/openid-configuration"
LOGIN_URL = "/api/users/auth/oidc/login"
DISCOVERY = {
    "authorization_endpoint": "https://idp.example/authorize",
    "token_endpoint": "https://idp.example/token",
    "userinfo_endpoint": "https://idp.example/userinfo",
}


@pytest.fixture
def clock(monkeypatch):
    from users.oauth import oidc_retry

    clock = SimpleNamespace(now=1000.0)
    monkeypatch.setattr(oidc_retry, "monotonic", lambda: clock.now)
    return clock


def _app():
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret")
    app.state.users = SimpleNamespace(
        settings=UsersSettings(
            oauth_oidc_client_id="test-client",
            oauth_oidc_client_secret="private-secret",
            oauth_oidc_discovery_url=DISCOVERY_URL,
            oauth_oidc_display_name="Company SSO",
        )
    )
    router = APIRouter(prefix="/api/users")
    register_oauth_routes(router)
    app.include_router(router)
    return app


@pytest.mark.anyio
async def test_failed_boot_keeps_button_and_returns_unavailable(httpx_mock, caplog, clock):
    httpx_mock.add_response(url=DISCOVERY_URL, status_code=503)
    app = _app()
    _build_oauth_clients(app)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(LOGIN_URL)
        assert response.status_code == 503
        assert response.json() == {"detail": "OAUTH_PROVIDER_UNAVAILABLE"}
        browser = await client.get(LOGIN_URL, headers={"accept": "text/html"})
        assert browser.status_code == 303
        assert browser.headers["location"] == "/users/login?oauth_error=signin_failed"

    assert app.state.users.oauth_providers == [{"name": "oidc", "display_name": "Company SSO"}]
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert DISCOVERY_URL in warnings[0].getMessage()
    assert "private-secret" not in caplog.text
    assert warnings[0].exc_info is None
    assert len(httpx_mock.get_requests()) == 1

    from simple_module_hosting.config.host_settings import HostSettings
    from users.auth_local.views import login_page

    app.state.host = SimpleNamespace(settings=HostSettings(login_redirect_url="/home/"))
    app.state.sm = SimpleNamespace(settings=SimpleNamespace(is_development=False), modules=[])
    request = Request({"type": "http", "app": app, "session": {}, "query_string": b""})
    inertia = SimpleNamespace(render=AsyncMock(return_value=Response()))
    await login_page(request, inertia)
    assert inertia.render.call_args.args[1]["oauth_providers"] == [
        {"name": "oidc", "display_name": "Company SSO"}
    ]


@pytest.mark.anyio
@pytest.mark.parametrize("outage", [{"status_code": 503}, {"text": "maintenance"}, {"json": {}}])
async def test_login_recovers_without_restart_and_keeps_domain_policy(httpx_mock, clock, outage):
    httpx_mock.add_response(url=DISCOVERY_URL, **outage)
    httpx_mock.add_response(url=DISCOVERY_URL, json=DISCOVERY)
    app = _app()
    app.state.users.settings.oauth_trusted_email_domains = {"oidc": ["staff.example"]}
    _build_oauth_clients(app)
    placeholder = app.state.users.oauth_clients["oidc"]
    clock.now += 30
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for _ in range(2):
            response = await client.get(LOGIN_URL)
            assert response.status_code == 302
            url = httpx.URL(response.headers["location"])
            assert str(url).startswith("https://idp.example/authorize?")
            assert url.params["client_id"] == "test-client"
            assert url.params["redirect_uri"] == "http://test/api/users/auth/oidc/callback"
            assert url.params["state"]
    recovered = app.state.users.oauth_clients["oidc"]
    assert recovered is not placeholder
    assert recovered.client is await placeholder.resolve_client()
    assert recovered.trusted_domains == frozenset({"staff.example"})
    assert len(httpx_mock.get_requests()) == 2


@pytest.mark.anyio
@pytest.mark.parametrize("outage", [{"status_code": 503}, {"text": "maintenance"}, {"json": {}}])
async def test_backoff_doubles_and_caps_at_ten_minutes(httpx_mock, clock, outage):
    httpx_mock.add_response(url=DISCOVERY_URL, status_code=503)
    httpx_mock.add_response(url=DISCOVERY_URL, is_reusable=True, **outage)
    app = _app()
    _build_oauth_clients(app)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for attempts, delay in enumerate((30, 60, 120, 240, 480, 600, 600), start=1):
            clock.now += delay - 0.01
            assert (await client.get(LOGIN_URL)).status_code == 503
            assert len(httpx_mock.get_requests()) == attempts
            clock.now += 0.01
            assert (await client.get(LOGIN_URL)).status_code == 503
            assert len(httpx_mock.get_requests()) == attempts + 1


@pytest.mark.anyio
@pytest.mark.parametrize("recovers", [False, True])
async def test_concurrent_logins_share_one_discovery_attempt(httpx_mock, clock, recovers):
    httpx_mock.add_response(url=DISCOVERY_URL, status_code=503)
    httpx_mock.add_response(
        url=DISCOVERY_URL,
        status_code=200 if recovers else 503,
        json=DISCOVERY,
        is_reusable=True,
    )
    app = _app()
    _build_oauth_clients(app)
    clock.now += 30
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        responses = await asyncio.gather(*(client.get(LOGIN_URL) for _ in range(8)))
    assert [r.status_code for r in responses] == [302 if recovers else 503] * 8
    assert len(httpx_mock.get_requests()) == 2


@pytest.mark.anyio
async def test_settings_reload_resets_backoff_and_can_disable_provider(httpx_mock, clock):
    from settings.contracts.events import SettingsReloaded
    from simple_module_core.eventing.events import EventBus
    from users.module import UsersModule

    httpx_mock.add_response(url=DISCOVERY_URL, status_code=503, is_reusable=True)
    app = _app()
    _build_oauth_clients(app)
    bus = EventBus()
    UsersModule().register_event_handlers(bus, app)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        clock.now += 30
        assert (await client.get(LOGIN_URL)).status_code == 503
        original = app.state.users.oauth_clients["oidc"]
        app.state.users.settings = app.state.users.settings.model_copy(
            update={"oauth_oidc_client_id": "new-client"}
        )
        await bus.publish(SettingsReloaded(package="users", changed=()))
        assert app.state.users.oauth_clients["oidc"] is not original
        assert len(httpx_mock.get_requests()) == 3
        clock.now += 29
        assert (await client.get(LOGIN_URL)).status_code == 503
        assert len(httpx_mock.get_requests()) == 3
        httpx_mock.add_response(url=DISCOVERY_URL, json=DISCOVERY)
        clock.now += 1
        response = await client.get(LOGIN_URL)
        assert response.status_code == 302
        assert httpx.URL(response.headers["location"]).params["client_id"] == "new-client"
        assert len(httpx_mock.get_requests()) == 4
        app.state.users.settings = UsersSettings()
        await bus.publish(SettingsReloaded(package="users", changed=()))
        assert (await client.get(LOGIN_URL)).status_code == 404
        assert app.state.users.oauth_providers == []


def test_boot_warning_redacts_credentials_query_and_exception(httpx_mock, caplog):
    app = _app()
    app.state.users.settings.oauth_oidc_discovery_url = (
        "https://operator:url-password@idp.example/.well-known/openid-configuration"
        "?token=query-secret#fragment-secret"
    )
    httpx_mock.add_exception(httpx.ConnectError("private-secret"))
    _build_oauth_clients(app)
    assert DISCOVERY_URL in caplog.text
    for secret in ("url-password", "query-secret", "fragment-secret", "private-secret"):
        assert secret not in caplog.text


def _blocked_discovery(httpx_mock, *, status_code=200):
    loop = asyncio.get_running_loop()
    started, release = asyncio.Event(), threading.Event()

    def reply(request):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(timeout=2), "test did not release discovery"
        return httpx.Response(status_code, json=DISCOVERY)

    httpx_mock.add_callback(reply, url=DISCOVERY_URL, is_reusable=True)
    return started, release


@pytest.mark.anyio
async def test_reload_during_discovery_cannot_restore_disabled_provider(httpx_mock, clock):
    httpx_mock.add_response(url=DISCOVERY_URL, status_code=503)
    app = _app()
    _build_oauth_clients(app)
    started, release = _blocked_discovery(httpx_mock)
    clock.now += 30
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        login = asyncio.create_task(client.get(LOGIN_URL))
        try:
            await asyncio.wait_for(started.wait(), timeout=1)
            app.state.users.settings = UsersSettings()
            _build_oauth_clients(app)
        finally:
            release.set()
        assert (await login).status_code == 404
    assert app.state.users.oauth_clients == {}
    assert app.state.users.oauth_providers == []


@pytest.mark.anyio
@pytest.mark.parametrize("elapsed", [0, 600])
@pytest.mark.parametrize("recovers", [False, True])
async def test_cancelled_login_keeps_shared_discovery_result(httpx_mock, clock, elapsed, recovers):
    httpx_mock.add_response(url=DISCOVERY_URL, status_code=503)
    app = _app()
    _build_oauth_clients(app)
    started, release = _blocked_discovery(httpx_mock, status_code=200 if recovers else 503)
    clock.now += 30
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        login = asyncio.create_task(client.get(LOGIN_URL))
        try:
            await asyncio.wait_for(started.wait(), timeout=1)
            login.cancel()
            with pytest.raises(asyncio.CancelledError):
                await login
        finally:
            release.set()
        clock.now += elapsed
        assert (await client.get(LOGIN_URL)).status_code == (302 if recovers else 503)
    assert len(httpx_mock.get_requests()) == 2
