"""E2E coverage for the app shell's home links, footer and sign-in error.

* the admin shell renders the shared ``ui`` catalog, never raw ``ui.*`` keys
  (#426), and its way back to the app follows the ``homeUrl`` shared prop
  rather than a hardcoded ``/dashboard/`` (#427);
* the default footer caption names the app, not the framework's licence (#428);
* a failed sign-in is announced to assistive technology (#437).
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

_RAW_UI_KEY = re.compile(r"\bui\.[a-z_]+\.[a-z_]+")


def _login(page: Page, username: str, password: str) -> None:
    page.goto("/users/login")
    page.locator("#email").fill(username)
    page.locator("#password").fill(password)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("**/dashboard/**", timeout=15_000)


def test_admin_shell_is_translated_and_links_home(
    page: Page, e2e_username: str, e2e_password: str
) -> None:
    _login(page, e2e_username, e2e_password)
    page.goto("/admin/users/")
    back = page.get_by_role("link", name="Back to app")
    expect(back).to_be_visible()
    assert not _RAW_UI_KEY.search(page.locator("body").inner_text())

    home = page.evaluate(
        "() => JSON.parse(document.getElementById('app').dataset.page).props.homeUrl"
    )
    assert home.startswith("/")
    expect(back).to_have_attribute("href", home)
    back.click()
    page.wait_for_url(f"**{home}**")


def test_default_footer_names_the_app_not_a_licence(page: Page) -> None:
    # The public landing page renders BrandingFooter; the sign-in page has no footer.
    page.goto("/")
    footer = page.locator("footer").last
    expect(footer).to_contain_text("©")
    assert "MIT" not in footer.inner_text()


def test_failed_sign_in_is_announced(page: Page, e2e_username: str) -> None:
    # One deliberate failure: the limiter allows five per window.
    page.goto("/users/login")
    page.locator("#email").fill(e2e_username)
    page.locator("#password").fill("definitely-not-the-password")
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_role("alert")).to_be_visible()
