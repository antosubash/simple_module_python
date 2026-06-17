"""End-to-end integration test for the branding flow.

Exercises the full path against a real ``create_app()``: PUT /api/branding
persists + hot-swaps the settings, the branding shared-props provider reads the
live value, ``InertiaLayoutDataMiddleware`` merges it, and an Inertia page
request carries the ``branding`` block in its shared props.
"""

from __future__ import annotations

import httpx


async def test_branding_appears_in_inertia_shared_props(
    app,
    authenticated_client: httpx.AsyncClient,
) -> None:
    # Default branding is present on every page.
    resp = await authenticated_client.get(
        "/dashboard/",
        headers={"X-Inertia": "true", "X-Inertia-Version": "1.0"},
    )
    assert resp.status_code == 200
    assert resp.json()["props"]["branding"]["appName"] == "SimpleModule"

    # Change it through the admin API.
    put = await authenticated_client.put(
        "/api/branding/",
        json={"app_name": "Acme End2End", "primary_color": "#abcdef"},
    )
    assert put.status_code == 200, put.text

    # The next page load reflects the new branding in its shared props.
    resp = await authenticated_client.get(
        "/dashboard/",
        headers={"X-Inertia": "true", "X-Inertia-Version": "1.0"},
    )
    assert resp.status_code == 200
    branding = resp.json()["props"]["branding"]
    assert branding["appName"] == "Acme End2End"
    assert branding["primaryColor"] == "#abcdef"
    assert branding["logoUrl"] is None
