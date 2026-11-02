"""AuthMiddleware lets a path no route serves reach the 404 (#473).

Only an *unmatched* path is let through anonymously; anything the router would
serve — including under the wrong method, or only via a trailing-slash
redirect — stays gated exactly as before.
"""

from __future__ import annotations

import httpx
import pytest
from auth.contracts.schemas import UserContext
from auth.middleware import AuthMiddleware
from auth.state import AuthState
from fastapi import APIRouter, FastAPI
from simple_module_core.redirect_safety import SESSION_NEXT_KEY
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

_USER = UserContext(id="u-1", email="a@example.com", name="A", roles=["admin"])


class _Provider:
    name = "stub"

    def __init__(self, user: UserContext | None = None) -> None:
        self._user = user

    async def resolve_user(self, request):
        return self._user

    def get_login_url(self, request, next_url=None):
        return "/stub/login"

    def get_logout_url(self, request):
        return "/stub/logout"

    def get_public_paths(self):
        return (("/stub/login",), ())

    def is_bearer_request(self, request):
        return request.headers.get("authorization", "").startswith("Bearer ")


def _build(user: UserContext | None = None) -> FastAPI:
    app = FastAPI()
    app.state.auth = AuthState(auth_provider=_Provider(user), principal_resolvers=[])

    async def ok():
        return {"ok": True}

    async def item(item_id: int):
        return {"id": item_id}

    async def session_dump(request: Request):
        return JSONResponse(dict(request.session))

    app.add_api_route("/dashboard", ok, methods=["GET"])
    app.add_api_route("/api/items", ok, methods=["GET"])
    app.add_api_route("/api/items/{item_id:int}", item, methods=["GET"])
    app.add_api_route("/stub/login", session_dump, methods=["GET"])
    admin = APIRouter(prefix="/admin")
    admin.add_api_route("/users", ok, methods=["GET"])
    admin.add_api_route("/roles/", ok, methods=["GET"])
    app.include_router(admin)

    app.add_middleware(AuthMiddleware)
    app.add_middleware(SessionMiddleware, secret_key="unknown-paths-secret")
    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test", follow_redirects=False)


async def test_anonymous_unknown_page_is_404_and_stores_no_next():
    async with _client(_build()) as c:
        resp = await c.get("/does-not-exist", headers={"sec-fetch-dest": "document"})
        assert resp.status_code == 404
        session = (await c.get("/stub/login")).json()
    assert SESSION_NEXT_KEY not in session


async def test_anonymous_unknown_api_is_404_json():
    async with _client(_build()) as c:
        resp = await c.get("/api/nope")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not Found"}


async def test_anonymous_unknown_api_with_bad_bearer_is_404():
    async with _client(_build()) as c:
        resp = await c.get("/api/nope", headers={"Authorization": "Bearer junk"})
    assert resp.status_code == 404


async def test_unknown_path_is_marked_anonymous_allowed_for_rate_limit():
    seen: dict = {}
    inner = _build()

    async def spy(scope, receive, send):
        await inner(scope, receive, send)
        seen.update(scope.get("state", {}))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=spy), base_url="http://t") as c:
        await c.get("/nope")
    assert seen.get("auth_public") is True


async def test_anonymous_existing_private_page_still_redirects_with_next():
    async with _client(_build()) as c:
        resp = await c.get("/dashboard?tab=1", headers={"sec-fetch-dest": "document"})
        assert resp.status_code == 302
        assert resp.headers["location"] == "/stub/login"
        session = (await c.get("/stub/login")).json()
    assert session[SESSION_NEXT_KEY] == "/dashboard?tab=1"


@pytest.mark.parametrize(
    ("method", "path", "status"),
    [
        ("GET", "/api/items", 401),
        ("GET", "/api/items/7", 401),
        ("POST", "/api/items", 401),  # wrong method on an existing route (405 when signed in)
        ("DELETE", "/dashboard", 302),
        ("HEAD", "/dashboard", 302),
        ("GET", "/admin/users", 302),  # route from an included router
        ("GET", "/admin/users/", 302),  # resolves only via the slash redirect
        ("GET", "/admin/roles", 302),  # the other direction of the slash redirect
        ("GET", "/api/items/", 401),
    ],
)
async def test_existing_routes_stay_gated(method, path, status):
    async with _client(_build()) as c:
        resp = await c.request(method, path)
    assert resp.status_code == status


async def test_converter_mismatch_is_an_unknown_path():
    # ``/api/items/{item_id:int}`` cannot serve ``/api/items/abc`` for anyone.
    async with _client(_build()) as c:
        resp = await c.get("/api/items/abc")
    assert resp.status_code == 404


async def test_signed_in_unknown_path_is_404():
    async with _client(_build(_USER)) as c:
        resp = await c.get("/does-not-exist")
    assert resp.status_code == 404


async def test_probe_failure_fails_closed(monkeypatch):
    import auth._route_match as rm

    def boom(router, probe):
        raise RuntimeError("router exploded")

    monkeypatch.setattr(rm, "_any_match", boom)
    async with _client(_build()) as c:
        resp = await c.get("/does-not-exist")
    assert resp.status_code == 302


async def test_full_app_unknown_paths_render_404_for_anonymous(client):
    page = await client.get("/does-not-exist", follow_redirects=False)
    assert page.status_code == 404
    assert "location" not in page.headers
    api = await client.get("/api/does-not-exist", follow_redirects=False)
    assert api.status_code == 404
    assert api.headers["content-type"].startswith("application/json")


async def test_full_app_private_routes_stay_gated_for_anonymous(client):
    page = await client.get("/admin/users", follow_redirects=False)
    assert page.status_code == 302
    assert "/login" in page.headers["location"]
    slash = await client.get("/admin/users/", follow_redirects=False)
    assert slash.status_code == 302
    assert "/login" in slash.headers["location"]
