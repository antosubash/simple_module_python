"""A replacement transports a real Users login using opaque server-side sessions."""

from secrets import token_urlsafe

import httpx
from fastapi import Depends, Request
from simple_module_hosting import replace_middleware
from simple_module_hosting.auth.csrf import CSRF_HEADER, RequiresCsrf, get_csrf_token
from simple_module_hosting.boot.app_builder import create_app
from simple_module_hosting.pipeline.session import SessionMiddleware
from simple_module_test.app.fixtures import _seed_setup_admin
from simple_module_test.db._schema import _create_all_tables
from starlette.datastructures import MutableHeaders
from starlette.middleware import Middleware
from starlette.requests import HTTPConnection
from starlette.responses import Response


class ServerSession(SessionMiddleware):
    """Test-only in-memory backend; inherits the session constructor contract."""

    def __init__(self, app, *, store, **kwargs):
        super().__init__(app, **kwargs)
        self.store = store

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        key = HTTPConnection(scope).cookies.get("backend_sid")
        scope["session"] = dict(self.store.get(key, {}))

        async def persist(message):
            if message["type"] == "http.response.start":
                cookie = Response()
                if scope["session"]:
                    new_key = token_urlsafe(32)
                    self.store[new_key] = dict(scope["session"])
                    cookie.set_cookie(
                        "backend_sid", new_key, httponly=True, samesite="lax", secure=self._secure
                    )
                elif key:
                    cookie.delete_cookie(
                        "backend_sid", httponly=True, samesite="lax", secure=self._secure
                    )
                if key:
                    self.store.pop(key, None)
                if "set-cookie" in cookie.headers:
                    MutableHeaders(scope=message).append("set-cookie", cookie.headers["set-cookie"])
            await send(message)

        await self.app(scope, receive, persist)


async def test_server_side_session_preserves_login_csrf_and_logout(settings):
    store = {}
    settings = settings.model_copy(update={"modules_enabled": ["Auth", "Users"]})

    def customize(app):
        replace_middleware(app, SessionMiddleware, Middleware(ServerSession, store=store))

    app = create_app(settings, customize=customize)

    @app.get("/api/users/auth/replacement-token")
    async def token(request: Request):
        return {"token": get_csrf_token(request)}

    @app.post("/api/users/auth/replacement-check", dependencies=[Depends(RequiresCsrf())])
    async def check():
        return {"ok": True}

    try:
        await _create_all_tables(app.state.sm.db.engine)
        await _seed_setup_admin(app)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver"
            ) as client,
        ):
            assert (await client.get("/api/users/me")).status_code == 401
            response = await client.post(
                "/api/users/auth/login",
                data={"username": "admin@test", "password": "test-password"},
            )
            assert response.status_code == 204, response.text
            key = client.cookies["backend_sid"]
            assert store[key]["user_id"]
            assert store[key]["expires_at"]
            assert "session" not in client.cookies
            cookie = response.headers["set-cookie"].lower()
            assert "httponly" in cookie and "samesite=lax" in cookie
            # Force the next request to authenticate only through the replacement session.
            client.cookies.delete(app.state.users.settings.cookie_name)
            assert (await client.get("/api/users/me")).json()["email"] == "admin@test"
            token = (await client.get("/api/users/auth/replacement-token")).json()["token"]
            assert (await client.post("/api/users/auth/replacement-check")).status_code == 403
            assert (
                await client.post("/api/users/auth/replacement-check", headers={CSRF_HEADER: token})
            ).status_code == 200
            assert (await client.post("/api/users/auth/logout")).status_code == 204
            assert (await client.get("/api/users/me")).status_code == 401
    finally:
        await app.state.sm.db.engine.dispose()


async def test_replacement_round_trips_and_clears_cookie(settings):
    """Exercise session transport without requiring a database connection."""
    store = {}
    app = create_app(
        settings,
        customize=lambda app: replace_middleware(
            app, SessionMiddleware, Middleware(ServerSession, store=store)
        ),
    )

    @app.post("/setup/session-probe")
    async def write(request: Request):
        request.session["marker"] = "persisted"
        return {"ok": True}

    @app.get("/setup/session-probe")
    async def read(request: Request):
        return {"marker": request.session.get("marker")}

    @app.delete("/setup/session-probe")
    async def clear(request: Request):
        request.session.clear()
        return {"ok": True}

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            assert (await client.post("/setup/session-probe")).status_code == 200
            assert client.cookies["backend_sid"] in store
            assert "session" not in client.cookies
            assert (await client.get("/setup/session-probe")).json() == {"marker": "persisted"}
            assert (await client.delete("/setup/session-probe")).status_code == 200
            assert "backend_sid" not in client.cookies
            assert not store
            assert (await client.get("/setup/session-probe")).json() == {"marker": None}
    finally:
        await app.state.sm.db.engine.dispose()
