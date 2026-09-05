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
    SESSION_REMEMBER_KEY,
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

    @app.post("/remember-session")
    def remember_session(request: Request) -> dict:
        """What the real sign-in does: record the window in the session."""
        request.session["user_id"] = "u1"
        request.session[SESSION_REMEMBER_KEY] = REMEMBER_WINDOW
        return {"ok": True}

    @app.post("/remember-forever")
    def remember_forever(request: Request) -> dict:
        request.session["user_id"] = "u1"
        request.session[SESSION_REMEMBER_KEY] = True
        return {"ok": True}

    @app.get("/touch")
    def touch(request: Request) -> dict:
        """Stands in for any authenticated page: reading the session is not
        enough to re-emit the cookie, but caching anything in it is — which is
        what resolving the signed-in user does on every request."""
        request.session["user_ctx"] = {"id": request.session.get("user_id")}
        return {"ok": True}

    @app.post("/forget")
    def forget(request: Request) -> dict:
        request.session.pop(SESSION_REMEMBER_KEY, None)
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
async def test_the_widened_window_survives_the_next_request(client):
    """The regression this whole mechanism exists for.

    Starlette re-emits the cookie on every response that touched the session,
    and resolving the signed-in user touches it. A window recorded only on the
    scope of the sign-in request would be silently rolled back to the default
    by the very next page load — "remember me" would mean fourteen days from
    the first click.
    """
    signed_in = await client.post("/remember-session")
    assert "Max-Age=2592000" in _session_cookie(signed_in)

    later = await client.get("/touch")
    assert "Max-Age=2592000" in _session_cookie(later)


@pytest.mark.anyio
async def test_the_scope_key_is_deliberately_one_response_only(client):
    """The escape hatch records nothing, so it does not outlive its response —
    which is exactly why the session flag exists."""
    await client.post("/remember")
    later = await client.get("/touch")
    assert f"Max-Age={SESSION_COOKIE_MAX_AGE}" in _session_cookie(later)


@pytest.mark.anyio
async def test_forgetting_the_flag_returns_to_the_default(client):
    """Clearing the session's remember record — what the auth provider does
    when it forgets who was signed in — must shorten the next cookie again."""
    await client.post("/remember-session")
    await client.post("/forget")
    later = await client.get("/touch")
    assert f"Max-Age={SESSION_COOKIE_MAX_AGE}" in _session_cookie(later)


@pytest.mark.anyio
async def test_a_boolean_flag_means_the_signature_window(client):
    """``True`` is accepted as well as a number of seconds — and must not be
    read as ``int(True)``, which would be a one-second cookie."""
    resp = await client.post("/remember-forever")
    assert f"Max-Age={SESSION_SIGNATURE_MAX_AGE}" in _session_cookie(resp)


@pytest.mark.anyio
async def test_a_plain_session_stays_at_the_default_on_later_requests(client):
    await client.post("/sign-in")
    later = await client.get("/touch")
    assert f"Max-Age={SESSION_COOKIE_MAX_AGE}" in _session_cookie(later)


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


def test_passing_max_age_is_refused_rather_than_ignored():
    """It used to be popped, so a deployment could believe it had shortened
    sessions when the value had gone straight in the bin."""
    import pytest

    with pytest.raises(TypeError, match="signature window"):
        SessionMiddleware(lambda scope, receive, send: None, "secret", max_age=60)


class TestClampFallsBackOnAnythingUnusable:
    """``_clamp``'s other branch. The suite covered a window *beyond* the
    signature max, but never a zero, negative or non-integer one — which is
    where the 14-day default comes from, and the branch a caller reaches by
    reading a bad value out of a session payload rather than by typing one.
    """

    @pytest.mark.parametrize(
        "value,why",
        [
            (0, "zero — a cookie that expires immediately is not a window"),
            (-1, "negative"),
            (None, "absent"),
            ("1209600", "a string that looks like a number"),
            (True, "bool is an int, and True must not read as one second"),
            (False, "the other bool"),
            (14.5, "float"),
        ],
    )
    def test_it_returns_the_default(self, value, why):
        from simple_module_hosting.session import SESSION_COOKIE_MAX_AGE, _clamp

        assert _clamp(value) == SESSION_COOKIE_MAX_AGE, why

    def test_a_usable_window_is_kept(self):
        from simple_module_hosting.session import _clamp

        assert _clamp(60) == 60

    def test_a_window_past_the_signature_is_capped(self):
        """A cookie the signer will not accept is worse than a shorter one: it
        fails at the end of a long absence rather than at sign-in."""
        from simple_module_hosting.session import SESSION_SIGNATURE_MAX_AGE, _clamp

        assert _clamp(SESSION_SIGNATURE_MAX_AGE * 2) == SESSION_SIGNATURE_MAX_AGE
