"""``RequiresCsrf`` skips API-token principals, and only them (#1178).

A personal access token or service key arrives in an ``Authorization`` header
a browser never attaches cross-site, so there is no ambient credential to
forge and no session token to echo. The skip reads the *authenticated*
principal (``request.state.user``, set by the auth middleware), never a
header: a cookie session that also sends ``Authorization: Bearer junk`` is
still a cookie session and still needs ``X-CSRF-Token``.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest
from fastapi import APIRouter, Depends, FastAPI, Request
from simple_module_hosting.auth.csrf import CSRF_HEADER, RequiresCsrf, get_csrf_token
from starlette.middleware.sessions import SessionMiddleware

_PRINCIPAL_HEADER = "x-test-principal"


@dataclass
class _Principal:
    auth_kind: str
    scopes: list[str] | None


_PRINCIPALS: dict[str, _Principal] = {
    "pat": _Principal("pat", ["feature_flags.edit"]),
    "service": _Principal("service", []),
    "session": _Principal("session", None),
    "bearer": _Principal("bearer", None),
    # Inconsistent shapes: neither half alone is a token principal.
    "scoped-session": _Principal("session", ["feature_flags.edit"]),
    "unscoped-pat": _Principal("pat", None),
}


def _app() -> FastAPI:
    app = FastAPI()
    router = APIRouter(dependencies=[Depends(RequiresCsrf())])

    @app.get("/token")
    def token(request: Request) -> dict:
        return {"token": get_csrf_token(request)}

    @router.post("/things")
    def create_thing() -> dict:
        return {"created": True}

    app.include_router(router)

    @app.middleware("http")
    async def fake_auth(request: Request, call_next):
        # Stands in for AuthMiddleware: the principal lands on request.state.
        name = request.headers.get(_PRINCIPAL_HEADER)
        request.state.user = _PRINCIPALS[name] if name else None
        return await call_next(request)

    app.add_middleware(SessionMiddleware, secret_key="test-secret")
    return app


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.parametrize("kind", ["pat", "service"])
async def test_token_principal_mutates_without_csrf_token(
    client: httpx.AsyncClient, kind: str
) -> None:
    resp = await client.post(
        "/things",
        headers={_PRINCIPAL_HEADER: kind, "Authorization": "Bearer smpat_x"},
    )
    assert resp.status_code == 200, resp.text


async def test_token_principal_skips_even_when_the_session_has_a_token(
    client: httpx.AsyncClient,
) -> None:
    await client.get("/token")
    resp = await client.post("/things", headers={_PRINCIPAL_HEADER: "pat"})
    assert resp.status_code == 200


@pytest.mark.parametrize("kind", ["session", "bearer", "scoped-session", "unscoped-pat"])
async def test_non_token_principal_still_needs_the_csrf_token(
    client: httpx.AsyncClient, kind: str
) -> None:
    await client.get("/token")
    resp = await client.post("/things", headers={_PRINCIPAL_HEADER: kind})
    assert resp.status_code == 403
    assert CSRF_HEADER in resp.json()["detail"]


async def test_cookie_session_with_junk_bearer_still_needs_the_csrf_token(
    client: httpx.AsyncClient,
) -> None:
    await client.get("/token")
    resp = await client.post(
        "/things",
        headers={_PRINCIPAL_HEADER: "session", "Authorization": "Bearer junk"},
    )
    assert resp.status_code == 403


async def test_bearer_header_without_a_principal_still_needs_the_csrf_token(
    client: httpx.AsyncClient,
) -> None:
    await client.get("/token")
    resp = await client.post("/things", headers={"Authorization": "Bearer smpat_forged"})
    assert resp.status_code == 403


async def test_session_principal_with_token_still_succeeds(client: httpx.AsyncClient) -> None:
    token = (await client.get("/token")).json()["token"]
    resp = await client.post("/things", headers={_PRINCIPAL_HEADER: "session", CSRF_HEADER: token})
    assert resp.status_code == 200
