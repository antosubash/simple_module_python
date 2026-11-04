import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_index_renders(page, e2e_username):
    page.goto("/__e2e/inertia/")
    expect(page.get_by_test_id("e2e-user-email")).to_have_text(e2e_username)
    expect(page.get_by_test_id("e2e-link-partial")).to_be_visible()


def test_link_navigation_is_client_side(page):
    page.goto("/__e2e/inertia/")
    page.evaluate("window.__marker = 'alive'")
    page.get_by_test_id("e2e-link-partial").click()
    expect(page).to_have_url("/__e2e/inertia/partial")
    expect(page.get_by_test_id("e2e-value-stamp")).to_be_visible()
    assert page.evaluate("window.__marker") == "alive"


def test_back_forward(page):
    page.goto("/__e2e/inertia/")
    page.evaluate("window.__marker = 'alive'")
    page.get_by_test_id("e2e-link-partial").click()
    expect(page.get_by_test_id("e2e-value-stamp")).to_be_visible()
    page.go_back()
    expect(page.get_by_test_id("e2e-user-email")).to_be_visible()
    expect(page).to_have_url("/__e2e/inertia/")
    page.go_forward()
    expect(page.get_by_test_id("e2e-value-stamp")).to_be_visible()
    assert page.evaluate("window.__marker") == "alive"


@pytest.mark.allow_resource_errors  # the 409 is the point of this test
def test_stale_asset_version_forces_full_reload(page):
    """A 409 from a mismatched X-Inertia-Version must make the client hard-reload."""
    page.goto("/__e2e/inertia/")
    page.evaluate("window.__marker = 'alive'")

    def stale(route):
        headers = dict(route.request.headers)
        if headers.get("x-inertia"):
            headers["x-inertia-version"] = "stale-version"
        route.continue_(headers=headers)

    page.route("**/__e2e/inertia/partial", stale)
    seen = []
    page.on(
        "response",
        lambda r: seen.append((r.status, r.url)) if "/__e2e/inertia/partial" in r.url else None,
    )
    with page.expect_navigation():
        page.get_by_test_id("e2e-link-partial").click()
    page.unroute("**/__e2e/inertia/partial")
    expect(page.get_by_test_id("e2e-value-stamp")).to_be_visible()
    assert page.evaluate("window.__marker") is None, "expected a full page reload"
    assert seen[0][0] == 409, seen
