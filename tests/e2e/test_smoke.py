"""End-to-end UI smoke tests.

Two browser-driven happy-path tests, both gated by the ``e2e`` marker:

* :func:`test_login_and_browse_smoke` — landing → Keycloak login →
  dashboard → products browse → logout. Minimal regression guard that
  proves auth and page rendering work end to end.

* :func:`test_products_crud_smoke` — builds on the browse smoke with
  the full create → edit → delete loop. Requires the Keycloak client
  to emit ``realm_access.roles`` in userinfo so ``RequiresPermission``
  lets the admin user through.

Requires a live stack. See docs/e2e-testing.md for setup.
"""

from __future__ import annotations

import re
import time

import pytest
from playwright.sync_api import Page, expect

_PRODUCTS_URL = re.compile(r"/products/?$")

pytestmark = pytest.mark.e2e


def _login(page: Page, username: str, password: str) -> None:
    """From landing, click Get Started and complete the Keycloak form."""
    # Landing renders a nav "Get Started" and a hero "Get Started"; either works.
    page.get_by_role("link", name="Get Started").first.click()
    page.locator("#username").fill(username)
    page.locator("#password").fill(password)
    page.locator("#kc-login").click()


def _login_and_land_on_dashboard(page: Page, username: str, password: str) -> None:
    """Shared setup: open landing, log in, wait for dashboard."""
    page.goto("/")
    expect(page.get_by_role("heading", name="Modular Monolith")).to_be_visible()
    _login(page, username, password)
    page.wait_for_url("**/dashboard/**", timeout=15_000)
    expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()


def test_login_and_browse_smoke(
    page: Page,
    e2e_username: str,
    e2e_password: str,
) -> None:
    _login_and_land_on_dashboard(page, e2e_username, e2e_password)
    # Welcome card — anchor on the CardTitle text which is unique on this page.
    expect(page.get_by_text("Welcome", exact=True)).to_be_visible()

    # Navigate directly: sidebar link is hidden below the lg breakpoint.
    page.goto("/products")
    expect(page.get_by_role("heading", name="Products")).to_be_visible()

    page.goto("/auth/logout")
    page.goto("/")
    expect(page.get_by_role("heading", name="Modular Monolith")).to_be_visible()


def test_products_crud_smoke(
    page: Page,
    e2e_username: str,
    e2e_password: str,
) -> None:
    """Full create → edit → delete loop against the live Products module.

    Requires the admin user's session to carry ``realm_access.roles``
    (set via the realm-export.json protocol mapper) so the
    ``products.create`` / ``.edit`` / ``.delete`` permission gates allow
    the calls.
    """
    _login_and_land_on_dashboard(page, e2e_username, e2e_password)

    # Millisecond-timestamped name keeps the test idempotent across reruns,
    # even if a prior run crashed before cleanup.
    product_name = f"Smoke Test Widget {int(time.time() * 1000)}"
    edited_name = f"{product_name} edited"

    page.goto("/products/create")
    expect(page.get_by_role("heading", name="Create Product")).to_be_visible()
    page.locator("#name").fill(product_name)
    page.locator("#description").fill("e2e smoke test")
    page.locator("#price").fill("9.99")
    page.get_by_role("button", name="Create Product").click()

    page.wait_for_url(_PRODUCTS_URL, timeout=15_000)
    created_row = page.get_by_role("row").filter(has_text=product_name)
    expect(created_row).to_be_visible(timeout=10_000)

    created_row.locator("a[href*='/edit']").click()
    page.wait_for_url("**/edit", timeout=10_000)
    page.locator("#name").fill(edited_name)
    page.get_by_role("button", name="Save Changes").click()

    page.wait_for_url(_PRODUCTS_URL, timeout=15_000)
    edited_row = page.get_by_role("row").filter(has_text=edited_name)
    expect(edited_row).to_be_visible(timeout=10_000)

    # Row has an edit link + a single <button> (the trash-icon delete trigger).
    edited_row.get_by_role("button").click()
    dialog = page.get_by_role("alertdialog")
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name="Delete").click()
    expect(edited_row).not_to_be_visible(timeout=10_000)
