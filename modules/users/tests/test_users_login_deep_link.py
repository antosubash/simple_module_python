"""An anonymous visit to a protected page should come back after login.

AuthMiddleware stashes the target in the session; the login view surfaces it
as ``login_redirect_url``. Before this existed the target was dropped and
every login landed on the configured default.

Filename is prefixed with the module name on purpose: no tests/ directory
here has an __init__.py, so test module basenames share one global namespace.
"""

from __future__ import annotations

import pytest


class TestDeepLinkAfterLogin:
    """An anonymous visit to a protected page should come back after login.

    AuthMiddleware stashes the target in the session; the login view surfaces
    it as ``login_redirect_url``. Before this existed the target was dropped
    and every login landed on the configured default.
    """

    @pytest.mark.anyio
    async def test_bounced_target_becomes_the_redirect_prop(self, anon_client):
        bounced = await anon_client.get("/admin/settings/", follow_redirects=False)
        assert bounced.status_code == 302

        resp = await anon_client.get(
            "/users/login",
            headers={"X-Inertia": "true", "X-Inertia-Version": "1.0"},
        )
        assert resp.json()["props"]["login_redirect_url"] == "/admin/settings/"

    @pytest.mark.anyio
    async def test_query_string_is_preserved(self, anon_client):
        await anon_client.get("/admin/settings/?tab=modules", follow_redirects=False)

        resp = await anon_client.get(
            "/users/login",
            headers={"X-Inertia": "true", "X-Inertia-Version": "1.0"},
        )
        assert resp.json()["props"]["login_redirect_url"] == "/admin/settings/?tab=modules"

    @pytest.mark.anyio
    async def test_reload_of_login_page_keeps_the_target(self, anon_client):
        """Read-not-pop: reloading the login page must not lose the deep link."""
        await anon_client.get("/admin/settings/", follow_redirects=False)

        for _ in range(2):
            resp = await anon_client.get(
                "/users/login",
                headers={"X-Inertia": "true", "X-Inertia-Version": "1.0"},
            )
            assert resp.json()["props"]["login_redirect_url"] == "/admin/settings/"

    @pytest.mark.anyio
    async def test_without_a_bounce_the_default_is_used(self, anon_client):
        resp = await anon_client.get(
            "/users/login",
            headers={"X-Inertia": "true", "X-Inertia-Version": "1.0"},
        )
        assert resp.json()["props"]["login_redirect_url"] == "/dashboard/"
