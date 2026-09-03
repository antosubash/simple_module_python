"""The session cookie's browser window is decided per request.

Starlette spends one number on two jobs — the cookie's ``Max-Age`` and the age
at which the signature stops verifying — which makes "keep me signed in for 30
days" unimplementable from an endpoint. These tests pin the split: the signer
accepts the long window always, the cookie asks for the short one unless a
request opts in.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI, Request
from simple_module_hosting.session import (
    SESSION_COOKIE_MAX_AGE,
    SESSION_COOKIE_MAX_AGE_KEY,
    SESSION_SIGNATURE_MAX_AGE,
    SessionMiddleware,
)

REMEMBER_WINDOW = 30 * 24 * 60 * 60


def _app() -> FastAPI:
    app = FastAPI()

    @app.post("/sign-in")
    def sign_in(request: Request) -> dict:
        request.session["user_id"] = "u1"
        return {"ok": True}

    @app.post("/remember")
    def remember(request: Request) -> dict:
        request.session["user_id"] = "u1"
        request.scope[SESSION_COOKIE_MAX_AGE_KEY] = REMEMBER_WINDOW
        return {"ok": True}

    @app.post("/absurd")
    def absurd(request: Request) -> dict:
        request.session["user_id"] = "u1"
        request.scope[SESSION_COOKIE_MAX_AGE_KEY] = 10 * 365 * 24 * 60 * 60
        return {"ok": True}

    @app.post("/sign-out")
    def sign_out(request: Request) -> dict:
        request.session.clear()
        return {"ok": True}

    @app.get("/who")
    def who(request: Request) -> dict:
        return {"user_id": request.session.get("user_id")}

    app.add_middleware(SessionMiddleware, secret_key="test-secret")
    return app


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _session_cookie(resp: httpx.Response) -> str:
    headers = [v for k, v in resp.headers.multi_items() if k.lower() == "set-cookie"]
    matching = [h for h in headers if h.startswith("session=")]
    assert matching, f"no session Set-Cookie in {headers!r}"
    return matching[-1]


@pytest.mark.anyio
async def test_an_ordinary_sign_in_keeps_the_fourteen_day_cookie(client):
    resp = await client.post("/sign-in")
    assert f"Max-Age={SESSION_COOKIE_MAX_AGE}" in _session_cookie(resp)
    assert "Max-Age=1209600" in _session_cookie(resp)


@pytest.mark.anyio
async def test_opting_in_widens_this_response_only(client):
    remembered = await client.post("/remember")
    assert "Max-Age=2592000" in _session_cookie(remembered)


@pytest.mark.anyio
async def test_a_window_beyond_the_signature_is_clamped(client):
    """A cookie the signer will not accept fails after a long absence — the
    worst possible moment — so it is never issued."""
    resp = await client.post("/absurd")
    assert f"Max-Age={SESSION_SIGNATURE_MAX_AGE}" in _session_cookie(resp)


@pytest.mark.anyio
async def test_the_cookie_still_carries_the_session(client):
    """The rewrite must touch Max-Age and nothing else."""
    await client.post("/remember")
    assert (await client.get("/who")).json()["user_id"] == "u1"


@pytest.mark.anyio
async def test_clearing_the_session_still_expires_the_cookie(client):
    """The clearing header carries an ``expires`` in the past and no Max-Age;
    the rewrite must leave it alone rather than resurrect the cookie."""
    await client.post("/sign-in")
    resp = await client.post("/sign-out")
    cookie = _session_cookie(resp)
    assert "expires=Thu, 01 Jan 1970" in cookie
    assert "Max-Age" not in cookie


@pytest.mark.anyio
async def test_other_cookies_are_left_alone():
    app = _app()

    @app.post("/both")
    def both(request: Request):
        from starlette.responses import JSONResponse

        request.session["user_id"] = "u1"
        resp = JSONResponse({"ok": True})
        resp.set_cookie("sm_auth", "token", max_age=99)
        return resp

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/both")
    headers = [v for k, v in resp.headers.multi_items() if k.lower() == "set-cookie"]
    assert any(h.startswith("sm_auth=") and "Max-Age=99" in h for h in headers)
