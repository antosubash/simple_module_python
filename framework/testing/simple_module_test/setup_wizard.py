"""Helpers for driving the ``/setup`` wizard from tests.

Every wizard mutation carries the session-bound CSRF token, so a test has to
do what the page does: load the wizard (which mints the token into the
session cookie and hands it out as the ``csrfToken`` prop) and echo it back
as ``X-CSRF-Token``.
"""

from __future__ import annotations

import httpx
from simple_module_hosting.csrf import CSRF_HEADER


def wizard_client(app) -> httpx.AsyncClient:
    """An anonymous client for *app*; it keeps the session cookie between calls."""
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


async def wizard_headers(client: httpx.AsyncClient) -> dict[str, str]:
    """Load the wizard as Inertia would and return the headers its forms send.

    Raises ``AssertionError`` when the wizard is closed (404) — a test that
    expected to post into it would otherwise fail with a confusing 403.
    """
    resp = await client.get("/setup", headers={"X-Inertia": "true"})
    assert resp.status_code == 200, f"wizard not open: {resp.status_code}"
    token = resp.json()["props"]["csrfToken"]
    return {CSRF_HEADER: token, "Accept": "application/json"}


async def post_step(
    client: httpx.AsyncClient, step_id: str, data: dict | None = None
) -> httpx.Response:
    """Submit *step_id*'s wizard form, CSRF token included."""
    headers = await wizard_headers(client)
    return await client.post(f"/setup/steps/{step_id}", json=data or {}, headers=headers)
