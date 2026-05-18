"""View-route smoke tests for dashboard, settings, and feature_flags.

The audit found these Inertia views had no behavioural coverage — only the
underlying service was tested. A typo in ``_PAGE_HOME`` or a forgotten import
in the views module would manifest only when a real user clicked the link.
"""

from __future__ import annotations

import pytest


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
    resp = await authenticated_client.get("/dashboard/doctor", follow_redirects=False)
    assert resp.status_code == 200, resp.text
    assert "data-page" in resp.text


@pytest.mark.anyio
async def test_settings_index_renders_for_admin(authenticated_client):
    """The Settings module's browse page is reachable for admins."""
    resp = await authenticated_client.get("/settings/", follow_redirects=False)
    assert resp.status_code == 200, resp.text
    assert "data-page" in resp.text


@pytest.mark.anyio
async def test_settings_modules_renders_for_admin(authenticated_client):
    """Per-module settings UI must render without error."""
    resp = await authenticated_client.get("/settings/modules", follow_redirects=False)
    assert resp.status_code == 200, resp.text
    assert "data-page" in resp.text


@pytest.mark.anyio
async def test_dashboard_index_redirects_anon_to_login(client):
    """An unauthenticated visit to ``/dashboard/`` must redirect to login.

    Confirms AuthMiddleware sits before the view router as documented.
    """
    resp = await client.get("/dashboard/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/users/login" in resp.headers["location"]
