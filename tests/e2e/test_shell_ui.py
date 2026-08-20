"""E2E smoke test for the app shell — breadcrumb, ⌘K palette, honest lists.

Covers the wireframe/hi-fi shell work end to end: the desktop topbar
renders a section-aware breadcrumb on sub-pages, the command palette
opens and navigates from the keyboard, list views clamp out-of-range
``?page=`` values instead of surfacing an error page, and searches treat
LIKE metacharacters as literal text.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def _login(page: Page, username: str, password: str) -> None:
    page.get_by_role("link", name="Log in").first.click()
    page.locator("#email").fill(username)
    page.locator("#password").fill(password)
    page.get_by_role("button", name="Log in").click()
    page.wait_for_url("**/dashboard/**", timeout=15_000)


def test_breadcrumb_names_the_section_on_sub_pages(
    page: Page, e2e_username: str, e2e_password: str
) -> None:
    page.goto("/")
    _login(page, e2e_username, e2e_password)

    page.goto("/users/admin/add")
    crumb = page.get_by_role("navigation", name="breadcrumb")
    expect(crumb.get_by_role("link", name="Users")).to_be_visible()
    expect(crumb.get_by_text("Add people")).to_be_visible()


def test_command_palette_opens_filters_and_navigates(
    page: Page, e2e_username: str, e2e_password: str
) -> None:
    page.goto("/")
    _login(page, e2e_username, e2e_password)

    page.keyboard.press("Control+k")
    palette = page.get_by_placeholder("Jump to…")
    expect(palette).to_be_visible()
    palette.fill("Audit")
    page.keyboard.press("Enter")
    page.wait_for_url("**/audit_log**", timeout=10_000)

    # Reopen and close with Escape — no navigation this time.
    page.keyboard.press("Control+k")
    expect(page.get_by_placeholder("Jump to…")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.get_by_placeholder("Jump to…")).not_to_be_visible()


def test_out_of_range_pages_clamp_instead_of_erroring(
    page: Page, e2e_username: str, e2e_password: str
) -> None:
    """A stale or hand-edited ?page= must render the list, never an error page."""
    page.goto("/")
    _login(page, e2e_username, e2e_password)

    for url in ("/admin/background-tasks/?page=0", "/admin/background-tasks/?page=99"):
        page.goto(url)
        expect(page.get_by_role("heading", name="Background Tasks")).to_be_visible()

    for url in ("/file-storage/?page=0", "/file-storage/?page=99"):
        page.goto(url)
        expect(page.get_by_role("heading", name="Files")).to_be_visible()


def test_user_search_treats_like_metacharacters_literally(
    page: Page, e2e_username: str, e2e_password: str
) -> None:
    """A lone "_" is a literal underscore, not the single-character wildcard."""
    page.goto("/")
    _login(page, e2e_username, e2e_password)

    page.goto("/users/admin?q=_")
    expect(page.get_by_text("No users match these filters")).to_be_visible()
