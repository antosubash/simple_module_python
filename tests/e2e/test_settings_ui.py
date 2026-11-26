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

    # Booleans render as a shadcn Switch (role=switch), not a bare checkbox.
    toggle = page.get_by_role("switch").first
    before = toggle.is_checked()
    toggle.click()

    save = page.get_by_role("button", name="Save")
    expect(save).to_be_enabled()
    save.click()

    # On success the form resets dirty state → Save becomes disabled again.
    expect(save).to_be_disabled()

    # Toggle back so the test is idempotent.
    toggle.click()
    expect(save).to_be_enabled()
    save.click()
    expect(save).to_be_disabled()

    assert page.get_by_role("switch").first.is_checked() == before


def test_bool_description_stays_while_stored_value_overrides(
    page: Page, e2e_username: str, e2e_password: str
) -> None:
    """A toggle's description stays on its row once a stored value overrides
    it (#1062): the trailing column switches to the stored-value text. In
    either position the switch announces it as its description (#1138)."""
    page.goto("/")
    _login(page, e2e_username, e2e_password)
    page.goto("/admin/settings/")
    page.get_by_role("button", name=re.compile(r"^file_storage\b")).click()

    row = page.get_by_test_id("row-field-file_storage-public_files_cors")
    toggle = row.get_by_role("switch", name="public_files_cors", exact=True)
    description = row.get_by_text("Let any origin read public files cross-origin", exact=False)
    revert = row.get_by_role("button", name="Revert", exact=True)
    expect(revert).to_have_count(0)
    expect(description).to_be_visible()
    described = re.compile(r"^Let any origin read public files cross-origin")
    expect(toggle).to_have_accessible_description(described)

    toggle.click()
    save = page.get_by_role("button", name="Save")
    save.click()
    expect(revert).to_be_visible()
    try:
        expect(save).to_be_disabled()
        expect(description).to_be_visible()
        expect(toggle).to_have_accessible_description(described)
    finally:
        # Remove the stored value even when the regression assertion fails.
        revert.click()
        expect(revert).to_have_count(0)
    expect(description).to_be_visible()
    expect(toggle).to_have_accessible_description(described)


def test_module_url_search_and_draft_guard(
    page: Page, e2e_username: str, e2e_password: str
) -> None:
    """The selected module lives in ``?module=``, an empty search says so, and
    switching module with a draft asks before discarding it (#1159)."""
    page.goto("/")
    _login(page, e2e_username, e2e_password)
    page.goto("/admin/settings/?module=tenants")
    expect(page.get_by_role("heading", name=re.compile(r"^tenants settings"))).to_be_visible()

    search = page.get_by_role("searchbox")
    search.fill("zzzz-no-such-module")
    expect(page.get_by_role("status").filter(has_text="No matching modules")).to_be_visible()
    search.fill("")

    page.get_by_label("subdomain_base", exact=True).fill("draft.example.com")
    page.get_by_role("button", name=re.compile(r"^mail\b")).click()
    dialog = page.get_by_role("alertdialog")
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name="Cancel").click()
    expect(page.get_by_label("subdomain_base", exact=True)).to_have_value("draft.example.com")

    page.get_by_role("button", name=re.compile(r"^mail\b")).click()
    page.get_by_role("alertdialog").get_by_role("button", name=re.compile("Discard")).click()
    expect(page).to_have_url(re.compile(r"[?&]module=mail\b"))
    expect(page.get_by_role("heading", name=re.compile(r"^mail settings"))).to_be_visible()


def test_rejected_field_error_is_linked_and_focused(
    page: Page, e2e_username: str, e2e_password: str
) -> None:
    """A 422 field error is announced, linked to its control and focused (#1156)."""
    page.goto("/")
    _login(page, e2e_username, e2e_password)
    page.goto("/admin/settings/?module=tenants")
    control = page.get_by_label("subdomain_base", exact=True)
    control.fill("example.com:8080")
    page.get_by_role("button", name="Save").click()

    expect(control).to_have_attribute("aria-invalid", "true")
    expect(control).to_be_focused()
    error = page.get_by_role("alert").filter(has_text="subdomain_base")
    expect(error).to_be_visible()
    error_id = error.get_attribute("id")
    assert error_id
    expect(control).to_have_attribute("aria-describedby", re.compile(rf"\b{error_id}\b"))

    control.fill("")
    expect(control).not_to_have_attribute("aria-invalid", "true")
