"""Token principals carry their row id and pass ``RequiresCsrf`` (#1178).

The resolver stamps ``token_id`` (the ``ApiToken`` row id) on PAT and service
principals so audit records can name the credential. ``RequiresCsrf`` admits
a resolved token principal without ``X-CSRF-Token``; a cookie session — even
one sending a junk ``Authorization`` header — is still checked.
"""

from __future__ import annotations

from typing import Any

import pytest
from _api_tokens_support import CSRF_HEADERS, PAT_URL, SERVICE_URL, create_pat
from fastapi import HTTPException
from simple_module_hosting.auth.csrf import RequiresCsrf
from starlette.requests import Request


async def _create_service_key(app: Any, actor) -> dict:
    app.state.sm.permissions.map_role("user", ["feature_flags.view"])
    async with actor(admin=True) as a:
        resp = await a.client.post(
            SERVICE_URL,
            json={
                "name": "k",
                "roles": ["user"],
                "scopes": ["feature_flags.view"],
                "expires_in_days": 30,
            },
            headers=CSRF_HEADERS,
        )
        assert resp.status_code == 201, resp.text
        return resp.json()


async def _resolve(app: Any, token: str) -> Request:
    """Resolve *token* as the auth middleware would and return the request."""
    from api_tokens.credentials.resolver import resolve_api_token

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [(b"authorization", f"Bearer {token}".encode())],
        "app": app,
        # A browser-less client still gets an (empty) session mounted.
        "session": {},
        "state": {},
    }
    request = Request(scope)
    principal = await resolve_api_token(request)
    assert principal is not None
    request.state.user = principal
    return request


async def test_pat_principal_carries_its_token_id(app, actor):
    async with actor(admin=True) as a:
        body = await create_pat(a.client, ["feature_flags.view"])
    request = await _resolve(app, body["token"])
    assert request.state.user.token_id == str(body["item"]["id"])
    assert request.state.user.auth_kind == "pat"


async def test_service_principal_carries_its_token_id(app, actor):
    body = await _create_service_key(app, actor)
    request = await _resolve(app, body["token"])
    assert request.state.user.token_id == str(body["item"]["id"])
    assert request.state.user.auth_kind == "service"


async def test_resolved_pat_passes_requires_csrf(app, actor):
    async with actor(admin=True) as a:
        body = await create_pat(a.client, ["feature_flags.view"])
    await RequiresCsrf()(await _resolve(app, body["token"]))


async def test_resolved_service_key_passes_requires_csrf(app, actor):
    body = await _create_service_key(app, actor)
    await RequiresCsrf()(await _resolve(app, body["token"]))


async def test_resolved_session_principal_still_needs_csrf(app, actor):
    async with actor(admin=True) as a:
        body = await create_pat(a.client, ["feature_flags.view"])
    request = await _resolve(app, body["token"])
    request.state.user.scopes = None
    request.state.user.auth_kind = "session"
    with pytest.raises(HTTPException) as exc:
        await RequiresCsrf()(request)
    assert exc.value.status_code == 403


_PAT_BODY = {"name": "x", "scopes": ["feature_flags.view"], "expires_in_days": 30}


async def test_cookie_session_without_csrf_token_is_refused(actor):
    async with actor(admin=True) as a:
        resp = await a.client.post(PAT_URL, json=_PAT_BODY)
    assert resp.status_code == 403
    assert "X-CSRF-Token" in resp.json()["detail"]


@pytest.mark.parametrize("junk", ["junk", "smpat_not-a-real-token"])
async def test_cookie_session_with_junk_bearer_is_refused(actor, junk):
    """A bearer header that resolves to no principal never falls back to the
    cookie: the auth middleware answers 401 before ``RequiresCsrf`` runs, so
    the junk header cannot buy the session a CSRF skip. (The framework test
    ``test_hosting_csrf_tokens`` pins the 403 for a session principal that
    does reach the dependency with a bearer header attached.)"""
    async with actor(admin=True) as a:
        resp = await a.client.post(
            PAT_URL, json=_PAT_BODY, headers={"Authorization": f"Bearer {junk}"}
        )
    assert resp.status_code == 401, resp.text
