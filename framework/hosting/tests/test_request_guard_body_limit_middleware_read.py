"""A browser-shaped oversized body read by a pre-router middleware is a 413, not a 500."""

from __future__ import annotations

import httpx
from simple_module_hosting._body_limit import BodyLimitMiddleware
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


class _FormGate(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        await request.body()
        return await call_next(request)


def _client() -> httpx.AsyncClient:
    async def ok(request: Request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/gate", ok, methods=["POST"])])
    app.add_middleware(_FormGate)
    app.add_middleware(BodyLimitMiddleware, max_bytes=100)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    )


async def test_middleware_body_read_over_limit_is_413_for_pages() -> None:
    async with _client() as c:
        r = await c.post("/gate", content=b"x" * 500, headers={"Accept": "text/html"})
    assert r.status_code == 413


async def test_middleware_body_read_within_limit_passes() -> None:
    async with _client() as c:
        r = await c.post("/gate", content=b"x" * 50, headers={"Accept": "text/html"})
    assert r.status_code == 200
