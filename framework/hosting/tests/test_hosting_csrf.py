"""Opt-in CSRF primitive for module mutation endpoints.

Field finding: with the framework offering only SameSite=Lax, the
pagebuilder module built its own session-bound token middleware — and every
content module after it would reinvent the same wheel with its own header
name and token-discovery convention. ``simple_module_hosting.csrf`` lifts
the proven design into the framework: one header (``X-CSRF-Token``), one
session key, one dependency modules opt into.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import APIRouter, Depends, FastAPI, Request
from simple_module_hosting.csrf import CSRF_HEADER, RequiresCsrf, get_csrf_token
from starlette.middleware.sessions import SessionMiddleware


def _app(*, with_session: bool = True) -> FastAPI:
    app = FastAPI()
    router = APIRouter(dependencies=[Depends(RequiresCsrf())])

    @app.get("/token")
    def token(request: Request) -> dict:
        return {"token": get_csrf_token(request)}

    @router.get("/things")
    def list_things() -> dict:
        return {"ok": True}

    @router.post("/things")
    def create_thing() -> dict:
        return {"created": True}

    app.include_router(router)
    if with_session:
        app.add_middleware(SessionMiddleware, secret_key="test-secret")
    return app


@pytest.fixture
async def csrf_client():
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestRequiresCsrf:
    async def test_token_endpoint_returns_a_token(self, csrf_client: httpx.AsyncClient) -> None:
        resp = await csrf_client.get("/token")
        assert resp.status_code == 200
        assert resp.json()["token"]

    async def test_safe_method_needs_no_token(self, csrf_client: httpx.AsyncClient) -> None:
        assert (await csrf_client.get("/things")).status_code == 200

    async def test_post_without_token_is_403(self, csrf_client: httpx.AsyncClient) -> None:
        resp = await csrf_client.post("/things")
        assert resp.status_code == 403
        assert CSRF_HEADER in resp.json()["detail"]

    async def test_post_with_wrong_token_is_403(self, csrf_client: httpx.AsyncClient) -> None:
        await csrf_client.get("/token")  # establish a session token
        resp = await csrf_client.post("/things", headers={CSRF_HEADER: "forged"})
        assert resp.status_code == 403

    async def test_post_with_non_ascii_token_is_403_not_500(
        self, csrf_client: httpx.AsyncClient
    ) -> None:
        """Header values are latin-1: a non-ASCII token must be rejected as
        403, not explode in str compare_digest (TypeError → 500)."""
        await csrf_client.get("/token")
        # raw latin-1 bytes: httpx's str path refuses non-ASCII, but a raw
        # client on the wire can send it and starlette will decode it
        resp = await csrf_client.post("/things", headers=[(CSRF_HEADER.encode(), b"caf\xe9-token")])
        assert resp.status_code == 403

    async def test_post_with_token_succeeds(self, csrf_client: httpx.AsyncClient) -> None:
        token = (await csrf_client.get("/token")).json()["token"]
        resp = await csrf_client.post("/things", headers={CSRF_HEADER: token})
        assert resp.status_code == 200
        assert resp.json() == {"created": True}

    async def test_token_is_stable_within_a_session(self, csrf_client: httpx.AsyncClient) -> None:
        first = (await csrf_client.get("/token")).json()["token"]
        second = (await csrf_client.get("/token")).json()["token"]
        assert first == second


class TestWithoutSessionMiddleware:
    """Bare test apps mount no SessionMiddleware — the primitive must not trap them."""

    async def test_enforcement_is_skipped_and_token_empty(self) -> None:
        transport = httpx.ASGITransport(app=_app(with_session=False))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            assert (await c.get("/token")).json()["token"] == ""
            assert (await c.post("/things")).status_code == 200
