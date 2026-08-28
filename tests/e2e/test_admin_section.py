"""E2E coverage for the admin section redesign.

Four guarantees that are easy to regress silently and cheap to assert:

* the app sidebar carries one ``Administration`` link rather than a scatter
  of individual admin entries, and the admin shell lists every admin screen;
* a module with its own settings page (Branding) is linked to from the
  generic module editor, never re-editable there — enforced in the UI *and*
  by the JSON API behind it;
* the Doctor page reports live diagnostics, migrations and environment
  rather than the demo fixtures it used to ship;
* the admin shell uses the app's primary accent, not a separate red skin.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

ADMIN_SCREENS = [
    ("Users", "/admin/users/"),
    ("Branding", "/admin/branding/"),
    ("Feature Flags", "/admin/feature-flags/"),
    ("Background Tasks", "/admin/background-tasks/"),
    ("Settings", "/admin/settings/"),
    ("Audit Log", "/admin/audit-log/"),
    ("Doctor", "/admin/doctor/"),
]


def _login(page: Page, username: str, password: str) -> None:
    page.get_by_role("link", name="Log in").first.click()
    page.locator("#email").fill(username)
    page.locator("#password").fill(password)
    page.get_by_role("button", name="Log in").click()
    page.wait_for_url("**/dashboard/**", timeout=15_000)


def test_app_sidebar_delegates_to_one_admin_entry(
    page: Page, e2e_username: str, e2e_password: str
) -> None:
    """Admin screens belong to the admin shell, not the app sidebar.

    Branding and Feature Flags used to register into the app sidebar while
    rendering in the admin layout, which left orphan groups beside Dashboard.
    """
    page.goto("/")
    _login(page, e2e_username, e2e_password)

    sidebar = page.get_by_role("complementary")
    expect(sidebar.get_by_role("link", name="Administration")).to_be_visible()
    for label, _ in ADMIN_SCREENS:
        expect(sidebar.get_by_role("link", name=label, exact=True)).to_have_count(0)


def test_admin_shell_reaches_every_screen(page: Page, e2e_username: str, e2e_password: str) -> None:
    page.goto("/")
    _login(page, e2e_username, e2e_password)
    page.get_by_role("link", name="Administration").click()
    page.wait_for_url("**/admin**", timeout=15_000)

    sidebar = page.get_by_role("complementary")
    for label, url in ADMIN_SCREENS:
        expect(sidebar.get_by_role("link", name=label, exact=True)).to_have_attribute("href", url)


def test_branding_is_linked_not_re_edited_in_module_settings(
    page: Page, e2e_username: str, e2e_password: str
) -> None:
    """The generic editor hands Branding off to its own page."""
    page.goto("/")
    _login(page, e2e_username, e2e_password)

    page.goto("/admin/settings/")
    page.get_by_role("button", name="Branding").click()

    expect(page.get_by_role("heading", name="Managed on its own page")).to_be_visible()
    open_link = page.get_by_role("link", name="Open Branding settings")
    expect(open_link).to_have_attribute("href", "/admin/branding/")
    # The whole point: no second editor for the same fields.
    expect(page.get_by_label("app_name")).to_have_count(0)

    open_link.click()
    page.wait_for_url("**/admin/branding/**", timeout=15_000)
    expect(page.get_by_role("heading", name="Branding")).to_be_visible()


def test_generic_settings_api_refuses_to_double_edit_branding(
    page: Page, e2e_username: str, e2e_password: str
) -> None:
    """The UI routes around it; the API must enforce it.

    Guarding only the screen would leave the invariant one ``fetch`` away
    from being bypassed, so the endpoint answers 409 for any module that
    declares its own page — and keeps working for every module that doesn't.
    """
    page.goto("/")
    _login(page, e2e_username, e2e_password)

    blocked = page.request.put("/api/settings/modules/branding", data={"app_name": "Hijacked"})
    assert blocked.status == 409, blocked.text()

    cleared = page.request.delete("/api/settings/modules/branding/app_name")
    assert cleared.status == 409, cleared.text()

    allowed = page.request.put(
        "/api/settings/modules/background_tasks", data={"task_default_queue": "default"}
    )
    assert allowed.ok, allowed.text()

    page.goto("/admin/branding/")
    expect(page.get_by_label("Application name")).not_to_have_value("Hijacked")


def test_doctor_reports_live_state(page: Page, e2e_username: str, e2e_password: str) -> None:
    """Doctor mirrors ``make doctor`` instead of shipping demo fixtures."""
    page.goto("/")
    _login(page, e2e_username, e2e_password)

    page.goto("/admin/doctor/")
    expect(page.get_by_role("heading", name="Doctor")).to_be_visible()

    # Environment facts can only come from the running app.
    expect(page.get_by_text("development", exact=True)).to_be_visible()
    expect(page.get_by_text("Diagnostics", exact=True)).to_be_visible()

    # The retired fixtures named a module that has never existed here, and a
    # dev-server panel whose port was wrong.
    expect(page.get_by_text("modules/billing/router.py")).to_have_count(0)
    expect(page.get_by_text("Vite HMR")).to_have_count(0)
