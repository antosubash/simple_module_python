"""``GET /api/_meta/openapi``: the live schema for API clients (#1178).

The CLI fetches the running server's schema with its token, so the route admits
tokens through ``host.openapi.read``, is never anonymous (not even with
``openapi_public``), and stays out of the schema it serves.
"""

from __future__ import annotations

import httpx
import pytest
from _api_tokens_support import admin_session, pat_for  # ty: ignore[import-not-found]
from feature_flags.core.constants import PERM_FEATURE_FLAGS_VIEW
from simple_module_core.access.permissions import PermissionRegistry
from simple_module_hosting.auth.host_permissions import HostPermissions
from simple_module_hosting.auth.meta_openapi import META_OPENAPI_PATH


@pytest.fixture
def settings(settings):
    # Serving /api/openapi.json anonymously must not make this route anonymous.
    return settings.model_copy(update={"openapi_public": True})


def _client(app, **headers: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers=headers
    )


async def _pat(app, scopes: list[str]) -> str:
    return await pat_for(app, await admin_session(app), scopes)


def test_permission_is_registered_on_the_app(app):
    registry: PermissionRegistry = app.state.sm.permissions
    assert HostPermissions.OPENAPI_READ == "host.openapi.read"
    assert HostPermissions.OPENAPI_READ in registry.all_permissions


async def test_anonymous_refused_even_with_openapi_public(app):
    async with _client(app) as c:
        assert (await c.get("/api/openapi.json")).status_code == 200
        assert (await c.get(META_OPENAPI_PATH)).status_code == 401


async def test_pat_without_permission_refused(app):
    token = await _pat(app, [PERM_FEATURE_FLAGS_VIEW])
    async with _client(app, Authorization=f"Bearer {token}") as c:
        assert (await c.get(META_OPENAPI_PATH)).status_code == 403


async def test_pat_with_permission_gets_schema_and_revalidates(app):
    token = await _pat(app, [HostPermissions.OPENAPI_READ])
    async with _client(app, Authorization=f"Bearer {token}") as c:
        resp = await c.get(META_OPENAPI_PATH)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body == app.openapi()
        assert META_OPENAPI_PATH not in body["paths"]
        assert "/api/_meta/whoami" in body["paths"]
        assert "private" in resp.headers["cache-control"]
        assert "no-cache" in resp.headers["cache-control"]
        etag = resp.headers["etag"]
        assert etag.startswith('W/"')

        again = await c.get(META_OPENAPI_PATH, headers={"If-None-Match": etag})
        assert again.status_code == 304
        assert again.content == b""
        assert again.headers["etag"] == etag
        assert "private" in again.headers["cache-control"]

        # The strong form and a list holding it also match (weak comparison).
        listed = await c.get(META_OPENAPI_PATH, headers={"If-None-Match": f'"x", {etag[2:]}'})
        assert listed.status_code == 304

        stale = await c.get(META_OPENAPI_PATH, headers={"If-None-Match": 'W/"stale"'})
        assert stale.status_code == 200


async def test_admin_session_gets_schema(authenticated_client, app):
    resp = await authenticated_client.get(META_OPENAPI_PATH)
    assert resp.status_code == 200, resp.text
    assert resp.json() == app.openapi()


def test_route_not_in_served_schema_and_gated(app):
    from simple_module_hosting.pipeline._route_access import check_unguarded_api_routes

    assert META_OPENAPI_PATH not in app.openapi()["paths"]
    assert not any(META_OPENAPI_PATH in d.message for d in check_unguarded_api_routes(app))


async def test_if_none_match_parsing_over_http(app):
    token = await _pat(app, [HostPermissions.OPENAPI_READ])
    async with _client(app, Authorization=f"Bearer {token}") as c:
        etag = (await c.get(META_OPENAPI_PATH)).headers["etag"]

        async def status(*values: str) -> int:
            headers = [("If-None-Match", v) for v in values]
            return (await c.get(META_OPENAPI_PATH, headers=headers)).status_code

        assert await status("other,*,other") == 200  # malformed, not a wildcard
        assert await status('"other,*,other"') == 200  # one quoted tag holding commas
        assert await status('"a", *') == 200  # `*` counts only as the whole value
        assert await status('W/"stale"', etag) == 304  # match in a second header line
        assert await status("*") == 304
        assert await status(f"{etag[:-1]}") == 200  # unterminated quote


@pytest.mark.parametrize(
    "fields, expected",
    [
        (['"abc"'], True),
        (['W/"abc"'], True),
        (['"x", W/"abc"'], True),
        (['"a,b", "abc"'], True),
        (['"a,abc"'], False),
        (["abc"], False),
        (['"abc" junk'], False),
        ([""], False),
        ([" * "], True),
        (['"x"', "*"], True),
        ([], False),
    ],
)
def test_matches_unit(fields, expected):
    from simple_module_hosting.auth.meta_openapi import _matches

    assert _matches(fields, 'W/"abc"') is expected
