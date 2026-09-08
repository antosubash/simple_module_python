"""View-route tests for the keycloak module's two interstitials.

The signed-out card had no route at all — ``pages/LoggedOut.tsx`` existed but
nothing rendered it, so ending a Keycloak session bounced straight back to the
redirect page. These tests pin the route into existence, keep it reachable
without a session (it is the page you land on *after* signing out), and pin the
realm the redirect card names.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
from simple_module_hosting.settings import Settings

_INERTIA_HEADERS = {"X-Inertia": "true", "X-Inertia-Version": "1.0"}
_SERVER_URL = "https://sso.acme.co"
_REALM = "acme"


async def _build_keycloak_app():
    """A host with keycloak as the active auth provider.

    ``SM_AUTH_PROVIDER`` is pinned to ``users`` for the whole suite, and
    ``select_auth_provider`` drops every provider but the preferred one — so
    the keycloak view routes are not even mounted on the shared ``app``
    fixture. Passing ``auth_provider`` to ``Settings`` outranks the env var.
    """
    from simple_module_db.base import all_module_bases
    from simple_module_hosting.app_builder import create_app
    from simple_module_hosting.migrations import resolve_head_revisions
    from sqlalchemy import text

    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="testing",
        secret_key="test-secret-key",
        multi_tenant=False,
        auth_provider="keycloak",
    )
    application = create_app(settings)

    async with application.state.sm.db.engine.begin() as conn:

        def _create(sync_conn):
            for base in all_module_bases:
                base.metadata.create_all(sync_conn)

        await conn.run_sync(_create)

        # Stamp every branch head so the boot-time migration check treats this
        # in-memory schema as current — one row per module branch label.
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version "
                "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        for head in resolve_head_revisions():
            await conn.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
                {"v": head},
            )

    ctx = application.router.lifespan_context(application)
    await ctx.__aenter__()
    keycloak_settings = application.state.keycloak.settings
    keycloak_settings.server_url = _SERVER_URL
    keycloak_settings.realm = _REALM
    return application, ctx


@pytest.fixture
async def keycloak_app():
    application, ctx = await _build_keycloak_app()
    yield application
    await ctx.__aexit__(None, None, None)


@pytest.fixture
async def keycloak_client(keycloak_app) -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=keycloak_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


class TestLoginPage:
    @pytest.mark.anyio
    async def test_login_page_names_the_realm_it_is_sending_you_to(self, keycloak_client):
        resp = await keycloak_client.get("/keycloak/login", headers=_INERTIA_HEADERS)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["component"] == "Keycloak/Login"
        assert body["props"]["realm_url"] == f"{_SERVER_URL}/realms/{_REALM}"


class TestLoggedOutPage:
    @pytest.mark.anyio
    async def test_logged_out_is_reachable_without_a_session(self, keycloak_client):
        """It is the page Keycloak redirects to *after* destroying the session."""
        resp = await keycloak_client.get("/keycloak/logged-out", follow_redirects=False)
        assert resp.status_code == 200, resp.text

    @pytest.mark.anyio
    async def test_logged_out_renders_its_own_component(self, keycloak_client):
        resp = await keycloak_client.get("/keycloak/logged-out", headers=_INERTIA_HEADERS)
        assert resp.status_code == 200, resp.text
        assert resp.json()["component"] == "Keycloak/LoggedOut"

    @pytest.mark.anyio
    async def test_logout_points_keycloak_back_at_the_signed_out_card(self, keycloak_client):
        resp = await keycloak_client.post("/keycloak/logout", follow_redirects=False)
        assert resp.status_code == 303
        assert "%2Fkeycloak%2Flogged-out" in resp.headers["location"]


class TestPublicPaths:
    def test_provider_exempts_the_signed_out_route(self):
        from keycloak.provider import KeycloakAuthProvider

        prefixes, _ = KeycloakAuthProvider().get_public_paths()
        assert "/keycloak/logged-out" in prefixes
