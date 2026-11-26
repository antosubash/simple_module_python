"""Over real HTTP: a token-admitting ``RequiresCsrf`` route takes API tokens (#1178).

A test-only mutation route carrying ``Authenticated()`` + ``TokenAllowed()`` +
``RequiresCsrf()`` is mounted on the fully built app, so the request runs the
whole pipeline (auth middleware, principal resolvers, token route guard)
before the CSRF dependency decides.
"""

from __future__ import annotations

from typing import Any

import pytest
from _api_tokens_support import CSRF_HEADERS, create_pat, create_service_key
from fastapi import APIRouter, Depends
from simple_module_hosting.auth.csrf import RequiresCsrf
from simple_module_hosting.auth.token_guard import Authenticated, TokenAllowed

_PROBE_URL = "/api/_test_csrf_probe/things"


@pytest.fixture
def probe_app(app: Any) -> Any:
    router = APIRouter(
        dependencies=[
            Depends(Authenticated()),
            Depends(TokenAllowed()),
            Depends(RequiresCsrf()),
        ]
    )

    @router.post(_PROBE_URL, status_code=201)
    async def create_thing() -> dict:
        return {"created": True}

    app.include_router(router)
    return app


async def test_pat_mutates_without_csrf_token(probe_app, actor, bearer):
    async with actor(admin=True) as a:
        token = (await create_pat(a.client, ["feature_flags.view"]))["token"]
    resp = await bearer("POST", _PROBE_URL, token)
    assert resp.status_code == 201, resp.text


async def test_service_key_mutates_without_csrf_token(probe_app, actor, bearer):
    probe_app.state.sm.permissions.map_role("user", ["feature_flags.view"])
    async with actor(admin=True) as a:
        resp = await create_service_key(
            a.client, name="k", roles=["user"], scopes=["feature_flags.view"]
        )
        assert resp.status_code == 201, resp.text
        token = resp.json()["token"]
    resp = await bearer("POST", _PROBE_URL, token)
    assert resp.status_code == 201, resp.text


async def test_cookie_session_without_csrf_token_is_refused(probe_app, actor):
    async with actor() as u:
        resp = await u.client.post(_PROBE_URL)
    assert resp.status_code == 403
    assert "X-CSRF-Token" in resp.json()["detail"]


async def test_cookie_session_with_csrf_token_succeeds(probe_app, actor):
    async with actor() as u:
        resp = await u.client.post(_PROBE_URL, headers=CSRF_HEADERS)
    assert resp.status_code == 201, resp.text
