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


class TestEveryProviderConsumesTheStashedTarget:
    """All three completion paths must honour ``SESSION_NEXT_KEY`` and clear it.

    ``AuthMiddleware`` writes the key for every bounced request, whichever
    provider the visitor eventually picks. A path that never reads it silently
    drops the deep link; a path that reads without popping leaves a stale
    target to fire on some later, unrelated visit to the login page. The OAuth
    callback did neither, so signing in with Google lost the deep link that the
    password and Keycloak paths kept — the exact per-module drift the shared
    key exists to prevent.

    Asserted against the source because these are three different flows in
    three packages, two of which need a live identity provider to exercise
    end to end; the thing worth pinning is that none of them forgets.
    """

    @staticmethod
    def _source(relative: str) -> str:
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        return (root / relative).read_text(encoding="utf-8")

    @pytest.mark.parametrize(
        "relative",
        [
            "modules/users/users/oauth/api.py",
            "modules/users/users/auth_local/api.py",
            "modules/keycloak/keycloak/endpoints/api.py",
        ],
    )
    def test_login_completion_paths_clear_the_stashed_target(self, relative: str) -> None:
        source = self._source(relative)
        assert "SESSION_NEXT_KEY" in source, (
            f"{relative} completes a login without touching the shared post-login destination key"
        )
        assert "pop(SESSION_NEXT_KEY" in source, (
            f"{relative} must pop SESSION_NEXT_KEY once login succeeds, or a "
            "stale deep link fires on a later visit to the login page"
        )

    @pytest.mark.parametrize(
        "relative",
        [
            "modules/users/users/oauth/api.py",
            "modules/keycloak/keycloak/endpoints/api.py",
        ],
    )
    def test_redirecting_providers_sanitise_the_target(self, relative: str) -> None:
        """The value lands in a Location header, so it is re-checked on the way
        out even though AuthMiddleware already validated it going in."""
        assert "safe_next_or_none" in self._source(relative)
