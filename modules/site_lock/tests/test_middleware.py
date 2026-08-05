"""SiteLockMiddleware gating behaviour."""

from __future__ import annotations

import httpx
from fastapi import FastAPI
from site_lock import constants as c
from site_lock.middleware import SiteLockMiddleware, password_fingerprint
from site_lock.settings import SiteLockSettings
from site_lock.state import SiteLockState
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse

SECRET = "test-site-lock-secret"
PASSWORD = "hunter2"


class _StubProvider:
    """Minimal AuthProvider stand-in for the admin-bypass path."""

    def __init__(self, user=None):
        self._user = user

    async def resolve_user(self, request):
        return self._user


def _build_app(settings: SiteLockSettings, *, provider=None) -> FastAPI:
    app = FastAPI()
    app.state.site_lock = SiteLockState(settings=settings)
    app.state.auth = type("_AuthState", (), {"auth_provider": provider})()

    async def _handler(path: str = ""):
        return JSONResponse({"ok": True})

    app.add_api_route("/{path:path}", _handler, methods=["GET", "POST"])
    app.add_middleware(SiteLockMiddleware)
    app.add_middleware(SessionMiddleware, secret_key=SECRET)
    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        follow_redirects=False,
    )


async def test_disabled_passes_everything_through() -> None:
    app = _build_app(SiteLockSettings())
    async with _client(app) as client:
        response = await client.get("/dashboard/")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


async def test_enabled_redirects_browser_to_the_gate() -> None:
    app = _build_app(SiteLockSettings(enabled=True, password=PASSWORD))
    async with _client(app) as client:
        response = await client.get("/dashboard/")
    assert response.status_code == 302
    assert response.headers["location"].startswith(c.UNLOCK_PATH)
    assert response.headers["cache-control"] == "no-store"


async def test_enabled_returns_403_json_for_api() -> None:
    app = _build_app(SiteLockSettings(enabled=True, password=PASSWORD))
    async with _client(app) as client:
        response = await client.get("/api/users/me")
    assert response.status_code == 403
    assert response.json() == {"detail": "Site is locked"}


async def test_bearer_request_gets_403_json_not_a_redirect() -> None:
    app = _build_app(SiteLockSettings(enabled=True, password=PASSWORD))
    async with _client(app) as client:
        response = await client.get("/dashboard/", headers={"Authorization": "Bearer x"})
    assert response.status_code == 403


async def test_health_is_never_gated() -> None:
    app = _build_app(SiteLockSettings(enabled=True, password=PASSWORD))
    async with _client(app) as client:
        response = await client.get("/health")
    assert response.status_code == 200


async def test_gate_page_is_served() -> None:
    app = _build_app(SiteLockSettings(enabled=True, password=PASSWORD, message="Soon"))
    async with _client(app) as client:
        response = await client.get(c.UNLOCK_PATH)
    assert response.status_code == 200
    assert 'name="password"' in response.text
    assert "Soon" in response.text


async def test_correct_password_unlocks_and_persists() -> None:
    app = _build_app(SiteLockSettings(enabled=True, password=PASSWORD))
    async with _client(app) as client:
        posted = await client.post(
            c.UNLOCK_PATH, data={"password": PASSWORD, "next": "/dashboard/"}
        )
        assert posted.status_code == 303
        assert posted.headers["location"] == "/dashboard/"
        # The session cookie now carries the unlock marker.
        followed = await client.get("/dashboard/")
    assert followed.status_code == 200


async def test_wrong_password_is_rejected() -> None:
    app = _build_app(SiteLockSettings(enabled=True, password=PASSWORD))
    async with _client(app) as client:
        posted = await client.post(c.UNLOCK_PATH, data={"password": "nope", "next": "/"})
        assert posted.status_code == 401
        followed = await client.get("/dashboard/")
    assert followed.status_code == 302


async def test_offsite_next_is_not_honoured_on_redirect() -> None:
    app = _build_app(SiteLockSettings(enabled=True, password=PASSWORD))
    async with _client(app) as client:
        posted = await client.post(
            c.UNLOCK_PATH, data={"password": PASSWORD, "next": "//evil.example"}
        )
    assert posted.headers["location"] == "/"


async def test_rotating_the_password_invalidates_existing_sessions() -> None:
    settings = SiteLockSettings(enabled=True, password=PASSWORD)
    app = _build_app(settings)
    async with _client(app) as client:
        await client.post(c.UNLOCK_PATH, data={"password": PASSWORD, "next": "/"})
        assert (await client.get("/dashboard/")).status_code == 200
        # Operator rotates the password via the settings UI.
        app.state.site_lock.settings = SiteLockSettings(enabled=True, password="new-one")
        response = await client.get("/dashboard/")
    assert response.status_code == 302


async def test_unsupported_method_on_the_gate_is_405() -> None:
    app = _build_app(SiteLockSettings(enabled=True, password=PASSWORD))
    async with _client(app) as client:
        response = await client.request("PUT", c.UNLOCK_PATH)
    assert response.status_code == 405


async def test_rate_limited_after_repeated_failures() -> None:
    app = _build_app(SiteLockSettings(enabled=True, password=PASSWORD))
    async with _client(app) as client:
        for _ in range(c.MAX_FAILURES):
            await client.post(c.UNLOCK_PATH, data={"password": "nope", "next": "/"})
        response = await client.post(c.UNLOCK_PATH, data={"password": PASSWORD, "next": "/"})
    assert response.status_code == 429


def test_fingerprint_changes_with_the_password() -> None:
    assert password_fingerprint("a") != password_fingerprint("b")
    assert password_fingerprint("a") == password_fingerprint("a")


class _User:
    def __init__(self, roles: list[str]) -> None:
        self.id = "11111111-2222-3333-4444-555555555555"
        self.roles = roles


async def test_admin_with_a_live_session_bypasses_the_gate() -> None:
    app = _build_app(
        SiteLockSettings(enabled=True, password=PASSWORD),
        provider=_StubProvider(_User(["admin"])),
    )
    async with _client(app) as client:
        response = await client.get("/dashboard/")
    assert response.status_code == 200


async def test_authenticated_non_admin_does_not_bypass() -> None:
    app = _build_app(
        SiteLockSettings(enabled=True, password=PASSWORD),
        provider=_StubProvider(_User(["user"])),
    )
    async with _client(app) as client:
        response = await client.get("/dashboard/")
    assert response.status_code == 302


async def test_admin_bypass_stamps_the_session_once() -> None:
    """After the first bypass the marker short-circuits further lookups."""
    calls = []

    class _CountingProvider(_StubProvider):
        async def resolve_user(self, request):
            calls.append(1)
            return _User(["admin"])

    app = _build_app(
        SiteLockSettings(enabled=True, password=PASSWORD),
        provider=_CountingProvider(),
    )
    async with _client(app) as client:
        await client.get("/dashboard/")
        await client.get("/dashboard/")
        await client.get("/dashboard/")
    assert len(calls) == 1


async def test_missing_provider_does_not_crash_the_gate() -> None:
    app = _build_app(SiteLockSettings(enabled=True, password=PASSWORD), provider=None)
    async with _client(app) as client:
        response = await client.get("/dashboard/")
    assert response.status_code == 302


async def test_provider_that_raises_is_treated_as_anonymous() -> None:
    class _BoomProvider:
        async def resolve_user(self, request):
            raise RuntimeError("provider exploded")

    app = _build_app(SiteLockSettings(enabled=True, password=PASSWORD), provider=_BoomProvider())
    async with _client(app) as client:
        response = await client.get("/dashboard/")
    assert response.status_code == 302
