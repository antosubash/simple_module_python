"""``SessionMiddleware`` never emits ``Cookie`` twice in ``Vary``.

Starlette appends ``Cookie`` whenever the session was touched, without looking
at what an inner layer (the tenants resolver) already listed.
"""

from __future__ import annotations

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from simple_module_hosting.session import SessionMiddleware


def _app(vary: str) -> FastAPI:
    app = FastAPI()

    @app.get("/touch")
    def touch(request: Request) -> JSONResponse:
        request.session["user_id"] = "u1"
        return JSONResponse({"ok": True}, headers={"Vary": vary})

    app.add_middleware(SessionMiddleware, secret_key="k" * 32)
    return app


async def _vary(app: FastAPI) -> list[str]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        return (await client.get("/touch")).headers.get_list("vary")


async def test_cookie_listed_by_an_inner_layer_is_not_repeated():
    assert await _vary(_app("Host, Cookie")) == ["Host, Cookie"]


async def test_star_is_left_alone():
    lines = await _vary(_app("*"))
    assert "*" in ", ".join(lines)
