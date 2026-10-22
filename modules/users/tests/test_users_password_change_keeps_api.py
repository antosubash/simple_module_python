"""The browser that changes its password keeps working on ``/api/*`` too.

A signed-in browser carries two credentials: the Starlette ``session`` cookie
the pages authenticate with, and the ``sm_auth`` access-token cookie behind
``fastapi_users.current_user`` on ``/api/users/me*``. The password change
re-stamped the first and deleted the row behind the second, so the profile page
kept rendering while every ``/api`` call it made answered 401 — including
"Sign out everywhere", which then failed silently.
"""

from __future__ import annotations

import httpx
import pytest

_ADMIN = {"username": "admin@example.com", "password": "AdminPass1!"}
_CHANGE = {"current_password": "AdminPass1!", "new_password": "BrandNewPass1!"}


async def _login(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/users/auth/login", data=_ADMIN)
    assert resp.status_code == 204, resp.text


def _client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


@pytest.mark.anyio
async def test_changing_browser_keeps_api_access_and_others_are_revoked(anon_client, users_app):
    other = _client(users_app)
    async with other:
        await _login(anon_client)
        await _login(other)
        assert (await other.get("/api/users/me")).status_code == 200

        resp = await anon_client.post("/api/users/me/password", json=_CHANGE)
        assert resp.status_code == 204, resp.text

        me = await anon_client.get("/api/users/me")
        assert me.status_code == 200, me.text
        page = await anon_client.get("/users/me", follow_redirects=False)
        assert page.status_code == 200, page.text

        # The browser signed in before the change is stranded on both paths.
        assert (await other.get("/api/users/me")).status_code == 401
        stale_page = await other.get("/users/me", follow_redirects=False)
        assert stale_page.status_code in (302, 303, 401), stale_page.text

        revoke = await anon_client.post("/api/users/me/sessions/revoke-all")
        assert revoke.status_code == 204, revoke.text
        assert (await anon_client.get("/api/users/me")).status_code == 401


@pytest.mark.anyio
async def test_a_remembered_sign_in_keeps_its_window(anon_client, users_app):
    resp = await anon_client.post("/api/users/auth/login", data={**_ADMIN, "remember": "true"})
    assert resp.status_code == 204, resp.text

    resp = await anon_client.post("/api/users/me/password", json=_CHANGE)
    assert resp.status_code == 204, resp.text
    cookie_name = users_app.state.users.settings.cookie_name
    set_cookie = next(
        v for v in resp.headers.get_list("set-cookie") if v.startswith(f"{cookie_name}=")
    )
    window = users_app.state.users.settings.remember_me_max_age_seconds
    assert f"Max-Age={window}" in set_cookie
