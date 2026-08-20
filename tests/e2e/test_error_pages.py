"""E2E tests for the error content-negotiation contract.

Browser navigations get the rendered Inertia error page — including on
``/api/*`` paths, because a navigation sends ``Accept: text/html`` — while
fetch-style callers get a JSON ``{"detail": ...}`` body. Pinned here
end-to-end because the split lives in middleware ordering + exception
handlers that unit tests can only exercise piecewise.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def _login(page: Page, username: str, password: str) -> None:
    page.goto("/users/login")
    page.locator("#email").fill(username)
    page.locator("#password").fill(password)
    page.get_by_role("button", name="Log in").click()
    page.wait_for_url("**/dashboard/**", timeout=15_000)


def test_missing_view_path_renders_error_page(
    page: Page, e2e_username: str, e2e_password: str
) -> None:
    """A browser navigation to a bogus view path gets the rendered error page."""
    _login(page, e2e_username, e2e_password)
    response = page.goto("/definitely/not/a/real/route")
    assert response is not None
    assert response.status == 404
    assert "text/html" in (response.headers.get("content-type") or "")
    # The Inertia error page mounts the app shell — raw JSON would have neither.
    expect(page.locator("#app")).to_be_attached()


def test_browser_navigation_to_missing_api_path_keeps_the_page(
    page: Page, e2e_username: str, e2e_password: str
) -> None:
    """Explicit text/html (a navigation) wins over the /api/* path rule."""
    _login(page, e2e_username, e2e_password)
    response = page.goto("/api/definitely-not-a-real-endpoint")
    assert response is not None
    assert response.status == 404
    assert "text/html" in (response.headers.get("content-type") or "")
    expect(page.locator("#app")).to_be_attached()


def test_fetch_callers_get_json_detail(page: Page, e2e_username: str, e2e_password: str) -> None:
    """API-shaped requests get the JSON error body, with and without Accept."""
    _login(page, e2e_username, e2e_password)

    explicit = page.request.get(
        "/api/definitely-not-a-real-endpoint",
        headers={"Accept": "application/json"},
    )
    assert explicit.status == 404
    assert "detail" in explicit.json()

    # No Accept preference at all — the /api/* path rule alone selects JSON.
    bare = page.request.get(
        "/api/definitely-not-a-real-endpoint",
        headers={"Accept": "*/*"},
    )
    assert bare.status == 404
    assert "detail" in bare.json()
