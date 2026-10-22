"""The ``csrfToken`` shared prop: signed-in sessions only (#504).

The frontend API client echoes it as ``X-CSRF-Token``. Anonymous pages never
carry it — minting would write the session (a ``Set-Cookie`` on every public
response, GH #349), and a page cacheable for anonymous visitors would hand one
visitor's token to the next.
"""

from __future__ import annotations

import base64
import json

import httpx
from fastapi import Depends
from simple_module_hosting._inertia_shared import csrf_shared_prop
from simple_module_hosting.csrf import CSRF_HEADER, RequiresCsrf
from starlette.requests import Request

_INERTIA = {"X-Inertia": "true"}
_PROBE = "/csrf-shared-prop-probe"


async def _props(client: httpx.AsyncClient, path: str) -> dict:
    resp = await client.get(path, headers=_INERTIA)
    assert resp.status_code == 200, resp.text
    return resp.json()["props"]


async def test_signed_in_page_carries_a_stable_token(authenticated_client) -> None:
    first = (await _props(authenticated_client, "/tenants/"))["csrfToken"]
    assert isinstance(first, str) and len(first) >= 32
    # Session-bound: the next page of the same session sends the same token.
    assert (await _props(authenticated_client, "/tenants/"))["csrfToken"] == first


async def test_shared_token_passes_requires_csrf(app, authenticated_client) -> None:
    async def _probe() -> dict[str, bool]:
        return {"ok": True}

    app.add_api_route(_PROBE, _probe, methods=["POST"], dependencies=[Depends(RequiresCsrf())])
    token = (await _props(authenticated_client, "/tenants/"))["csrfToken"]

    assert (await authenticated_client.post(_PROBE)).status_code == 403
    ok = await authenticated_client.post(_PROBE, headers={CSRF_HEADER: token})
    assert ok.status_code == 200, ok.text


async def test_anonymous_page_has_no_token(client) -> None:
    resp = await client.get("/users/login", headers=_INERTIA)
    assert resp.status_code == 200, resp.text
    assert "csrfToken" not in resp.json()["props"]
    # The full document of a page a module may mark cacheable stays token-free too.
    doc = await client.get("/users/login", headers={"Accept": "text/html"})
    assert doc.status_code == 200
    assert "csrfToken" not in doc.text


def test_helper_needs_a_signed_in_session() -> None:
    with_session = Request({"type": "http", "session": {}})
    assert csrf_shared_prop(with_session, is_authenticated=False) == {}
    assert with_session.scope["session"] == {}  # nothing minted for anonymous
    # No SessionMiddleware (bare apps): nothing to bind a token to.
    assert csrf_shared_prop(Request({"type": "http"}), is_authenticated=True) == {}
    token = csrf_shared_prop(with_session, is_authenticated=True)["csrfToken"]
    assert token == with_session.scope["session"]["sm_csrf_token"]


async def test_json_api_call_does_not_mint_a_token(app, authenticated_client) -> None:
    """Only a rendered page resolves the token (it is lazy), so a JSON call
    neither writes the session nor sets a cookie because of it."""

    async def _json() -> dict[str, bool]:
        return {"ok": True}

    app.add_api_route("/api/csrf-lazy-probe", _json, methods=["GET"])
    resp = await authenticated_client.get("/api/csrf-lazy-probe")
    assert resp.status_code == 200, resp.text
    # Starlette re-issues a non-empty session cookie; what matters is that it
    # carries no CSRF token the request minted.
    for header in resp.headers.get_list("set-cookie"):
        if header.startswith("session="):
            payload = header.split("=", 1)[1].split(";", 1)[0].split(".", 1)[0]
            claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
            assert "sm_csrf_token" not in claims
