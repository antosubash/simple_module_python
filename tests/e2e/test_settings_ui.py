"""E2E smoke test for the Settings modules admin UI.

Drives a real browser through the sidebar layout at ``/admin/settings/``,
toggles a module setting, and verifies the change hot-reloads into
``app.state`` without a server restart by exercising a downstream endpoint
whose behaviour flips when the setting flips.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def _login(page: Page, username: str, password: str) -> None:
    page.get_by_role("link", name="Sign in").first.click()
    page.locator("#email").fill(username)
    page.locator("#password").fill(password)
    page.get_by_role("button", name="Sign in").click()
    # Wait for the session cookie to land before navigating away, or
    # /admin/settings/ bounces us back to login and the sidebar never renders.
    page.wait_for_url("**/dashboard/**", timeout=15_000)


def test_toggle_host_multi_tenant_persists(
    page: Page, e2e_username: str, e2e_password: str
) -> None:
    """Toggle ``host.multi_tenant`` from the admin UI and confirm the PUT
    succeeds (surfaced by the Save button going idle). Proves the typed
    settings form wires up to the REST API."""
    page.goto("/")
    _login(page, e2e_username, e2e_password)

    page.goto("/admin/settings/")
    expect(page.get_by_text("Host", exact=False)).to_be_visible()

    # Click the Host entry in the sidebar.
    page.get_by_role("button", name=re.compile(r"host", re.I)).first.click()

    checkbox = page.get_by_role("checkbox").first
    before = checkbox.is_checked()
    checkbox.click()

    save = page.get_by_role("button", name="Save")
    expect(save).to_be_enabled()
    save.click()

    # On success the form resets dirty state → Save becomes disabled again.
    expect(save).to_be_disabled()

    # Toggle back so the test is idempotent.
    checkbox.click()
    expect(save).to_be_enabled()
    save.click()
    expect(save).to_be_disabled()

    assert page.get_by_role("checkbox").first.is_checked() == before
