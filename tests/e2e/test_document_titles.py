"""E2E regression test: the browser tab names the page, not just the app.

The failure mode is silent and total. Inertia's head manager only replaces
elements carrying the ``inertia`` attribute; anything else in ``<head>`` it
leaves alone and *appends* beside. The root template shipped a plain
``<title>``, so every page ended up with two title elements — the static brand
name first, Inertia's page-specific one second — and the browser takes the
first in document order. Every tab read as the bare app name, and no
``<Head title>`` anywhere in the app had any effect.

Nothing else catches this. The title renders, the page renders, every
role-and-name assertion still passes; only reading ``document.title`` shows it.
Asserting the element *count* matters as much as the text: a second, unmanaged
title reintroduces the bug the moment one is added back to the template.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

# (path, the page-specific fragment its title must carry)
_TITLED_PAGES = [
    ("/dashboard/", "Dashboard"),
    ("/admin", "Administration"),
]


def _login(page: Page, username: str, password: str) -> None:
    page.goto("/")
    page.get_by_role("link", name="Sign in").first.click()
    page.locator("#email").fill(username)
    page.locator("#password").fill(password)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("**/dashboard/**", timeout=15_000)


def test_login_page_title_names_the_page(page: Page) -> None:
    """Checked signed-out too: the sign-in page is the first tab a visitor
    sees, and it is served by the same template."""
    page.goto("/users/login")
    expect(page).to_have_title("Login — SimpleModule", timeout=10_000)


def test_signed_out_page_has_exactly_one_title_element(page: Page) -> None:
    """Two titles is the actual defect — the text assertions only fail
    because of the ordering it produces."""
    page.goto("/users/login")
    expect(page).to_have_title("Login — SimpleModule", timeout=10_000)
    assert page.locator("title").count() == 1


@pytest.mark.parametrize(("path", "fragment"), _TITLED_PAGES)
def test_page_title_names_the_page(
    page: Page, e2e_username: str, e2e_password: str, path: str, fragment: str
) -> None:
    _login(page, e2e_username, e2e_password)
    page.goto(path)
    # Waits for hydration: the server-rendered title is the bare app name until
    # the head manager commits, so reading straight after goto races it.
    expect(page).to_have_title(f"{fragment} — SimpleModule", timeout=10_000)
    assert page.locator("title").count() == 1


def test_error_page_title_names_the_status(
    page: Page, e2e_username: str, e2e_password: str
) -> None:
    """Signed in on purpose: to an anonymous visitor an unknown path is an
    auth bounce, not a 404, so this would assert against the login page."""
    _login(page, e2e_username, e2e_password)
    page.goto("/no-such-page-anywhere")
    expect(page).to_have_title("Page Not Found — SimpleModule", timeout=10_000)
