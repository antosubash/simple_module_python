"""View-route smoke tests for dashboard, settings, and feature_flags.

The audit found these Inertia views had no behavioural coverage — only the
underlying service was tested. A typo in ``_PAGE_HOME`` or a forgotten import
in the views module would manifest only when a real user clicked the link.
"""

from __future__ import annotations

import httpx
import pytest
from simple_module_test.fixtures import forge_session_cookie


@pytest.fixture
async def plain_user_client(app):
    """A signed-in account holding no admin role — Doctor exposes migration
    status, module list and system info, so this must not be enough to see it."""
    from users.models import User

    async with app.state.sm.db.session_factory() as session:
        user = User(
            email="plain-doctor@example.com",
            hashed_password="x",
            is_active=True,
            is_verified=True,
        )
        session.add(user)
        await session.commit()
        user_id = str(user.id)

    signed = forge_session_cookie(app.state.sm.settings.secret_key, {"user_id": user_id})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", cookies={"session": signed}
    ) as client:
        yield client


@pytest.mark.anyio
async def test_dashboard_index_renders_for_admin(authenticated_client):
    """``/dashboard/`` must respond 200 and produce an Inertia payload."""
    resp = await authenticated_client.get("/dashboard/", follow_redirects=False)
    assert resp.status_code == 200, resp.text
    # Inertia full-page response is HTML wrapping a ``data-page`` JSON blob.
    assert "data-page" in resp.text, "Dashboard view didn't render an Inertia page"


@pytest.mark.anyio
async def test_dashboard_doctor_renders_for_admin(authenticated_client):
    """The doctor sub-page mirrors the same route shape."""
    resp = await authenticated_client.get("/admin/doctor/", follow_redirects=False)
    assert resp.status_code == 200, resp.text
    assert "data-page" in resp.text


@pytest.mark.anyio
async def test_dashboard_doctor_rejects_a_non_admin(plain_user_client: httpx.AsyncClient):
    """A signed-in account with no admin role must not reach the doctor panel."""
    resp = await plain_user_client.get("/admin/doctor/", follow_redirects=False)
    assert resp.status_code == 403, resp.text[:400]


@pytest.mark.anyio
async def test_settings_index_renders_for_admin(authenticated_client):
    """The section root now leads with the per-module forms."""
    resp = await authenticated_client.get("/admin/settings/", follow_redirects=False)
    assert resp.status_code == 200, resp.text
    assert "data-page" in resp.text


@pytest.mark.anyio
async def test_settings_store_renders_for_admin(authenticated_client):
    """The raw key/value store moved off the root but stays reachable."""
    resp = await authenticated_client.get("/admin/settings/store", follow_redirects=False)
    assert resp.status_code == 200, resp.text
    assert "data-page" in resp.text


@pytest.mark.anyio
async def test_settings_modules_url_still_resolves(authenticated_client):
    """Existing links and bookmarks to /settings/modules must not break."""
    resp = await authenticated_client.get("/admin/settings/modules", follow_redirects=False)
    assert resp.status_code == 308, resp.text
    assert resp.headers["location"].endswith("/admin/settings/")


@pytest.mark.anyio
async def test_dashboard_index_redirects_anon_to_login(client):
    """An unauthenticated visit to ``/dashboard/`` must redirect to login.

    Confirms AuthMiddleware sits before the view router as documented.
    """
    resp = await client.get("/dashboard/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/users/login" in resp.headers["location"]


@pytest.mark.anyio
async def test_doctor_reports_real_diagnostics(authenticated_client):
    """The doctor page ships live checks, migrations and dev-server rows.

    Guards against the panel regressing to hardcoded demo data: the values
    asserted here can only come from the running app. The per-panel detail
    lives in ``test_doctor_props.py``; this is the route-level smoke test.
    """
    resp = await authenticated_client.get(
        "/admin/doctor/",
        headers={"X-Inertia": "true", "X-Inertia-Version": "1.0"},
    )
    assert resp.status_code == 200, resp.text
    props = resp.json()["props"]

    assert props["checks"], "the check catalogue is never empty"
    for check in props["checks"]:
        assert check["status"] in {"pass", "warn", "fail", "unknown"}

    # The test fixtures stamp alembic at head, so every listed revision must
    # read as applied and nothing may be pending.
    assert props["migrations"]
    assert all(row["applied"] for row in props["migrations"])
    assert props["stats"]["pending_migrations"] == 0

    assert [row["name"] for row in props["dev_server"]["rows"]] == ["vite", "api", "worker"]
