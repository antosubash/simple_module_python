"""AuthMiddleware tolerates duck-typed principals."""

from __future__ import annotations

import httpx
from auth.core.state import AuthState
from auth.web.middleware import AuthMiddleware
from fastapi import FastAPI, Request
from simple_module_core.web.public_routes import PublicRouteRegistry
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse


class _Provider:
    name = "stub"

    def __init__(self, user):
        self._user = user

    async def resolve_user(self, request):
        return self._user

    def get_login_url(self, request, next_url=None):
        return "/stub/login"

    def get_logout_url(self, request):
        return "/stub/logout"

    def is_bearer_request(self, request):
        return False


async def test_duck_typed_principal_without_auth_kind_is_tolerated():
    """A custom provider's principal need not carry ``auth_kind``/``token_id``."""
    from types import SimpleNamespace

    principal = SimpleNamespace(id="u1", email="d@example.com", roles=[], permissions=[])
    app = FastAPI()
    app.state.auth = AuthState(auth_provider=_Provider(principal), principal_resolvers=[])
    app.state.public_routes = PublicRouteRegistry()

    async def _ok(request: Request):
        return JSONResponse({"ok": True})

    app.add_api_route("/ping", _ok, methods=["GET"])
    app.add_middleware(AuthMiddleware)
    app.add_middleware(SessionMiddleware, secret_key="s")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        resp = await c.get("/ping")
    assert resp.status_code == 200
