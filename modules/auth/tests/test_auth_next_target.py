"""Only top-level navigations may become the post-login target (#416)."""

from __future__ import annotations

import httpx
import pytest
from auth.middleware import AuthMiddleware
from auth.state import AuthState
from fastapi import FastAPI, Request
from simple_module_core.redirect_safety import SESSION_NEXT_KEY
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse

SECRET = "test-next-target-secret"


class _StubProvider:
    name = "stub"

    async def resolve_user(self, request):
        return None

    def get_login_url(self, request, next_url=None):
        return "/stub/login"

    def get_logout_url(self, request):
        return "/stub/logout"

    def get_public_paths(self):
        return (("/stub/login", "/stub/public/"), ())

    def is_bearer_request(self, request):
        return False


def _build_app(provider) -> FastAPI:
    app = FastAPI()
    app.state.auth = AuthState(auth_provider=provider, principal_resolvers=[])

    # /static/ is framework-public, so this reads the session without auth.
    async def _next(request: Request):
        return JSONResponse({"next": request.session.get(SESSION_NEXT_KEY)})

    async def _any(path: str = ""):
        return JSONResponse({})

    app.add_api_route("/static/next", _next, methods=["GET"])
    app.add_api_route("/{path:path}", _any, methods=["GET"])
    app.add_middleware(AuthMiddleware)
    app.add_middleware(SessionMiddleware, secret_key=SECRET)
    return app


CASES = [
    ({"Sec-Fetch-Dest": "image", "Sec-Fetch-Mode": "no-cors"}, None),  # favicon
    ({"Sec-Fetch-Dest": "script", "Sec-Fetch-Mode": "no-cors"}, None),
    ({"Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors"}, None),  # fetch()
    ({"Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate"}, "/protected/page"),
    ({"Sec-Fetch-Mode": "navigate"}, "/protected/page"),
    ({"X-Inertia": "true", "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors"}, "/protected/page"),
    ({}, "/protected/page"),  # no metadata: previous behaviour
]


@pytest.mark.parametrize(("headers", "expected"), CASES)
async def test_only_navigations_record_the_target(headers, expected):
    seen: list[str | None] = []

    class _Recording(_StubProvider):
        def get_login_url(self, request, next_url=None):
            seen.append(next_url)
            return "/stub/login"

    app = _build_app(_Recording())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        resp = await c.get("/protected/page", headers=headers)
        recorded = (await c.get("/static/next")).json()["next"]
    assert resp.status_code == 302
    assert resp.headers["location"] == "/stub/login"
    assert seen == [expected]
    assert recorded == expected


async def test_a_subresource_does_not_overwrite_a_recorded_target():
    """The bug: the sign-in page's favicon request replaced the real target."""
    app = _build_app(_StubProvider())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        nav = {"Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate"}
        assert (await c.get("/protected/page", headers=nav)).status_code == 302
        icon = {"Sec-Fetch-Dest": "image", "Sec-Fetch-Mode": "no-cors"}
        resp = await c.get("/favicon.ico", headers=icon)
        assert resp.status_code == 302  # the redirect itself is unchanged
        recorded = (await c.get("/static/next")).json()["next"]
    assert recorded == "/protected/page"
