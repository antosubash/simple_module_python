"""The session cookie is ``Secure`` outside development (#495).

CSRF defence rests on ``SameSite=Lax`` alone, so a session cookie that can
travel over plain HTTP — the first request before HSTS is cached, a
misconfigured proxy — undermines it. Development and testing run on
``http://localhost`` and keep the cookie usable there.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import Request
from simple_module_hosting._phase_helpers import session_cookie_is_secure
from simple_module_hosting.settings import Settings
from simple_module_test.database import database_url_for_tests

_PROBE = "/__session_probe"


def _settings(**overrides: object) -> Settings:
    return Settings(
        database_url=database_url_for_tests(),
        environment="testing",
        secret_key="test-secret-key",
        auth_provider="users",
        **overrides,
    )


@pytest.mark.parametrize(
    ("environment", "explicit", "expected"),
    [
        ("production", None, True),
        ("staging", None, True),
        ("development", None, False),
        ("testing", None, False),
        ("production", False, False),  # plain-HTTP install opting out
        ("development", True, True),
    ],
)
def test_secure_resolution(environment: str, explicit: bool | None, expected: bool) -> None:
    settings = Settings.model_construct(environment=environment, session_cookie_secure=explicit)
    assert session_cookie_is_secure(settings) is expected


async def _session_set_cookie(app) -> str:
    async def probe(request: Request) -> dict[str, bool]:
        request.session["probe"] = True
        return {"ok": True}

    app.add_api_route(_PROBE, probe)
    app.state.public_routes.add_exact(_PROBE)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(_PROBE)
    assert resp.status_code == 200, resp.text
    cookies = [c for c in resp.headers.get_list("set-cookie") if c.startswith("session=")]
    assert cookies, resp.headers
    return cookies[0].lower()


class TestSecureCookieOn:
    @pytest.fixture
    def settings(self) -> Settings:
        return _settings(session_cookie_secure=True)

    async def test_set_cookie_is_secure(self, app) -> None:
        cookie = await _session_set_cookie(app)
        assert "; secure" in cookie
        assert "httponly" in cookie and "samesite=lax" in cookie


class TestSecureCookieDefaultInTesting:
    @pytest.fixture
    def settings(self) -> Settings:
        return _settings()

    async def test_set_cookie_is_not_secure_over_local_http(self, app) -> None:
        cookie = await _session_set_cookie(app)
        assert "; secure" not in cookie
